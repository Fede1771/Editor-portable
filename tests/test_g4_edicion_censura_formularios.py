"""Pruebas del Grupo 4: Edición de texto, censura, geometría con rotación/CropBox y formularios.
Cubre: H06, H07, H16, H17, H18, H21, H22, H30, H45, N02.
"""
from __future__ import annotations

import os
import pymupdf as fitz
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QLineEdit, QListWidget, QComboBox

from app import content_ops, forms, operations
from app.dialogs import FillFormsDialog
from app.doc_tab import DocTab
from app.viewer import PdfView


# ---------------------------------------------------------------------------
# H06 & H07: replace_text_block y add_text_box no deben perder texto ni mentir
# ---------------------------------------------------------------------------
def test_h06_replace_text_block_impossible_fit_preserves_original():
    """H06: Si el texto nuevo es imposible de encajar, debe lanzar ValueError y conservar el texto original."""
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((20, 40), "ORIGINAL_TEXT", fontsize=12)
    bbox = page.search_for("ORIGINAL_TEXT")[0]

    impossible_text = "MUY_LARGO " * 500
    with pytest.raises(ValueError):
        content_ops.replace_text_block(
            doc,
            0,
            bbox,
            impossible_text,
            fontsize=12.0,
            autofit=True,
        )

    # El texto original debe seguir presente en la página
    assert "ORIGINAL_TEXT" in page.get_text("text")
    doc.close()


def test_h07_add_text_box_impossible_fit_raises():
    """H07: Si add_text_box no logra insertar el texto ni siquiera expandiendo, debe lanzar ValueError."""
    doc = fitz.open()
    doc.new_page(width=200, height=100)
    impossible_text = "TEXTO_IMPOSIBLE " * 600

    with pytest.raises(ValueError):
        content_ops.add_text_box(
            doc,
            0,
            fitz.Rect(20, 20, 80, 40),
            impossible_text,
            fontsize=14.0,
        )
    doc.close()


# ---------------------------------------------------------------------------
# H45: redact_search_phrase debe eliminar secretos en texto, widgets y notas
# ---------------------------------------------------------------------------
def test_h45_redact_search_phrase_removes_widgets_and_notes(tmp_path):
    """H45: Buscar y censurar debe eliminar el secreto en texto normal, widgets de formulario y notas."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    secret = "SECURITY_SECRET"

    # 1. Texto normal
    page.insert_text((50, 60), f"Dato público y {secret} en texto", fontsize=11)

    # 2. Widget de formulario con el secreto
    w = fitz.Widget()
    w.field_name = "campo_secreto"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(50, 100, 250, 130)
    w.field_value = f"Valor con {secret}"
    page.add_widget(w)

    # 3. Nota / comentario con el secreto
    annot = page.add_text_annot(fitz.Point(50, 180), f"Nota interna: {secret}")
    annot.update()

    matches = content_ops.redact_search_phrase(doc, secret)
    assert matches >= 2

    out_pdf = tmp_path / "redacted_h45.pdf"
    doc.save(str(out_pdf), garbage=4, deflate=True)
    doc.close()

    reopened = fitz.open(str(out_pdf))
    p0 = reopened[0]
    assert secret not in p0.get_text("text")
    for rw in p0.widgets():
        assert secret not in str(rw.field_value or "")
    for ra in p0.annots():
        assert secret not in str(ra.info.get("content", "") or "")
    reopened.close()


def test_h45_redact_search_phrase_across_readonly_widgets_and_pages(tmp_path):
    """H45: Cuando una frase aparece en múltiples páginas y dentro de 8 widgets ReadOnly/normales, quedan 0 tras guardar/reabrir."""
    doc = fitz.open()
    term = "EXPEDIENTE_9988"
    for p in range(3):
        page = doc.new_page(width=400, height=400)
        page.insert_text((40, 40), f"Encabezado {term} pág {p+1}", fontsize=11)
        for k in range(3):
            w = fitz.Widget()
            w.field_name = f"ro_field_{p}_{k}"
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.field_flags = fitz.PDF_FIELD_IS_READ_ONLY
            w.rect = fitz.Rect(40, 80 + k * 45, 300, 110 + k * 45)
            w.field_value = f"Trámite {term} bloque {k}"
            page.add_widget(w)

    hits = content_ops.redact_search_phrase(doc, term)
    assert hits >= 12
    out_pdf = tmp_path / "multi_redacted.pdf"
    doc.save(str(out_pdf), garbage=4, deflate=True)
    doc.close()

    reopened = fitz.open(str(out_pdf))
    for page in reopened:
        assert len(page.search_for(term)) == 0
        assert term not in page.get_text("text")
        for w in page.widgets():
            assert term.lower() not in str(w.field_value or "").lower()
    reopened.close()


# ---------------------------------------------------------------------------
# H16 & H17: Coordenadas con rotación propia/CropBox y arrastre entre páginas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_h16_viewer_coordinates_with_page_rotation_and_cropbox(qapp, rot):
    """H16: _map_point, _map_rect y viewport_to_page_point deben coincidir con rotation_matrix en 0/90/180/270."""
    doc = fitz.open()
    page = doc.new_page(width=200, height=400)
    page.set_cropbox(fitz.Rect(10, 20, 190, 380))
    page.insert_text((30, 60), "HELLO")
    page.set_rotation(rot)

    view = PdfView(doc)
    view.resize(800, 600)
    view.set_zoom(1.0)

    search_rect = page.search_for("HELLO")[0]
    center_pt = fitz.Point((search_rect.x0 + search_rect.x1) / 2, (search_rect.y0 + search_rect.y1) / 2)

    # El punto mapeado al espacio de página mostrada debe coincidir con center_pt * page.rotation_matrix
    mapped_pt = view._map_point(0, center_pt)
    expected_pt = center_pt * page.rotation_matrix
    assert abs(mapped_pt.x() - expected_pt.x) < 1e-2
    assert abs(mapped_pt.y() - expected_pt.y) < 1e-2

    # Y al invertir desde el viewport debe recuperar center_pt en coordenadas de la API de PyMuPDF
    prect = view._page_rects[0]
    vp_pt = QPointF(
        prect.x() + mapped_pt.x() - view.horizontalScrollBar().value(),
        prect.y() + mapped_pt.y() - view.verticalScrollBar().value(),
    )
    pno, roundtrip_pt = view.viewport_to_page_point(vp_pt)
    assert pno == 0
    assert roundtrip_pt is not None
    assert abs(roundtrip_pt.x - center_pt.x) < 1e-2
    assert abs(roundtrip_pt.y - center_pt.y) < 1e-2
    doc.close()


def test_h17_cross_page_drag_does_not_mix_coordinates(qapp):
    """H17: Un arrastre que inicia en la página 0 y termina en la página 1 debe acotarse a la página 0."""
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.new_page(width=200, height=200)

    view = PdfView(doc)
    view.resize(800, 800)
    view.set_zoom(1.0)

    p0_rect = view._page_rects[0]
    p1_rect = view._page_rects[1]
    dx = view.horizontalScrollBar().value()
    dy = view.verticalScrollBar().value()

    # Iniciar cerca del borde inferior de la página 0 (y=180) y arrastrar hasta y=20 de la página 1
    p1_vp = QPointF(p0_rect.left() + 50 - dx, p0_rect.top() + 180 - dy)
    p2_vp = QPointF(p1_rect.left() + 100 - dx, p1_rect.top() + 20 - dy)

    pno, rect = view.viewport_to_page_rect(p1_vp, p2_vp)
    assert pno == 0
    assert rect is not None
    # No debe mezclar y=20 de la página 1 con y=180 de la página 0; debe ir de 180 a 200 (borde inferior de pág 0)
    assert rect.y0 >= 179.0
    assert rect.y1 <= 200.0
    doc.close()


# ---------------------------------------------------------------------------
# H18: add_background con CropBox desplazado debe cubrir toda la región visible
# ---------------------------------------------------------------------------
def test_h18_add_background_with_cropbox_covers_visible_area():
    """H18: add_background debe colorear toda la región visible incluso cuando CropBox tiene origen != (0,0)."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.set_cropbox(fitz.Rect(50, 60, 250, 260))

    operations.add_background(doc, [0], (1.0, 0.0, 0.0))
    pix = page.get_pixmap(alpha=False)
    # Esquina superior izquierda visible (5, 5) debe ser roja, no blanca
    r, g, b = pix.pixel(5, 5)[:3]
    assert r > 220 and g < 30 and b < 30
    # Esquina inferior derecha visible también debe ser roja
    r2, g2, b2 = pix.pixel(pix.width - 5, pix.height - 5)[:3]
    assert r2 > 220 and g2 < 30 and b2 < 30
    doc.close()


# ---------------------------------------------------------------------------
# H30: Edición de texto no debe mezclar colores ni fusionar estilos distintos
# ---------------------------------------------------------------------------
def test_h30_find_and_replace_text_preserves_distinct_styles():
    """H30: Texto negro normal y texto rojo en negrita en la misma línea no deben mezclarse en un solo estilo."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((40, 80), "NormalNegro", fontname="helv", fontsize=12, color=(0, 0, 0))
    page.insert_text((130, 80), "NegritaRojo", fontname="hebo", fontsize=12, color=(1, 0, 0))

    r_norm = page.search_for("NormalNegro")[0]
    r_bold = page.search_for("NegritaRojo")[0]

    info_norm = content_ops.find_text_block_at(
        page, fitz.Point((r_norm.x0 + r_norm.x1) / 2, (r_norm.y0 + r_norm.y1) / 2)
    )
    info_bold = content_ops.find_text_block_at(
        page, fitz.Point((r_bold.x0 + r_bold.x1) / 2, (r_bold.y0 + r_bold.y1) / 2)
    )

    assert info_norm is not None
    assert info_norm["text"] == "NormalNegro"
    assert info_norm["fontname"] == "helv"
    assert info_norm["color"] == (0.0, 0.0, 0.0)

    assert info_bold is not None
    assert info_bold["text"] == "NegritaRojo"
    assert info_bold["fontname"] == "hebo"
    assert info_bold["color"] == (1.0, 0.0, 0.0)
    doc.close()


# ---------------------------------------------------------------------------
# H21, H22, N02: Formularios (ListBox multiselección, nombres repetidos, errores)
# ---------------------------------------------------------------------------
def test_h21_listbox_multiselect_and_combobox(qapp):
    """H21: ListBox multiselección y ComboBox deben usar controles adecuados y persistir múltiples valores."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    w_combo = fitz.Widget()
    w_combo.field_name = "mi_combo"
    w_combo.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    w_combo.rect = fitz.Rect(40, 40, 200, 70)
    w_combo.choice_values = ["A", "B", "C"]
    w_combo.field_value = "A"
    page.add_widget(w_combo)

    w_list = fitz.Widget()
    w_list.field_name = "mi_lista"
    w_list.field_type = fitz.PDF_WIDGET_TYPE_LISTBOX
    w_list.field_flags = getattr(fitz, "PDF_CH_FIELD_IS_MULTI_SELECT", 1 << 21)
    w_list.rect = fitz.Rect(40, 90, 200, 160)
    w_list.choice_values = ["A", "B", "C"]
    w_list.field_value = "A"
    page.add_widget(w_list)

    # Configurar /V como array [ (A) (B) ] en el ListBox multiselección
    for w in page.widgets():
        if w.field_name == "mi_lista":
            doc.xref_set_key(w.xref, "V", "[(A)(B)]")

    fields = forms.get_form_fields(doc)
    by_name = {f["name"]: f for f in fields}
    assert by_name["mi_combo"]["type"] == "ComboBox"
    assert by_name["mi_lista"]["type"] == "ListBox"
    assert by_name["mi_lista"].get("multi_select") is True
    assert by_name["mi_lista"]["value"] == ["A", "B"]

    dlg = FillFormsDialog(fields)
    vals = dlg.values()
    assert vals["mi_lista"] == ["A", "B"]

    # Cambiar selección a ["B", "C"] y actualizar documento
    updated = forms.update_form_fields(doc, {"mi_combo": "C", "mi_lista": ["B", "C"]})
    assert updated == 2

    fields_after = {f["name"]: f for f in forms.get_form_fields(doc)}
    assert fields_after["mi_combo"]["value"] == "C"
    assert fields_after["mi_lista"]["value"] == ["B", "C"]
    doc.close()


def test_h22_repeated_field_names_synchronize_in_dialog(qapp):
    """H22: Dos controles con el mismo nombre de campo deben sincronizarse; editar el primero actualiza el valor final."""
    fields = [
        {"page": 0, "name": "cliente", "label": "Cliente", "type": "Text", "value": "Viejo", "choices": [], "read_only": False, "is_signature": False},
        {"page": 1, "name": "cliente", "label": "Cliente", "type": "Text", "value": "Viejo", "choices": [], "read_only": False, "is_signature": False},
    ]
    dlg = FillFormsDialog(fields)
    line_edits = dlg.findChildren(QLineEdit)
    assert len(line_edits) == 2

    # Editar el PRIMER control debe reflejarse en values() y en el segundo control
    line_edits[0].setText("Nuevo Cliente")
    assert line_edits[1].text() == "Nuevo Cliente"
    assert dlg.values()["cliente"] == "Nuevo Cliente"


def test_n02_form_update_error_not_silenced_and_rolls_back(qapp, monkeypatch):
    """N02: Si falla la actualización de un segundo campo, no debe silenciarse ni dejar edición parcial."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    for idx, name in enumerate(("campo1", "campo2")):
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(40, 40 + idx * 50, 200, 70 + idx * 50)
        w.field_value = "old"
        page.add_widget(w)

    tab = DocTab("", doc)
    orig_update = fitz.Widget.update
    call_count = {"n": 0}

    def flaky_update(self):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("Fallo simulado en el segundo widget")
        return orig_update(self)

    monkeypatch.setattr(fitz.Widget, "update", flaky_update)

    with pytest.raises(RuntimeError):
        tab.run_edit(lambda d: forms.update_form_fields(d, {"campo1": "new", "campo2": "new"}))

    # Al fallar el segundo widget, run_edit debe haber hecho rollback y ambos campos deben seguir en 'old'
    vals_after = {f["name"]: f["value"] for f in forms.get_form_fields(tab.doc)}
    assert vals_after["campo1"] == "old"
    assert vals_after["campo2"] == "old"
    assert tab.modified is False
    tab.doc.close()
