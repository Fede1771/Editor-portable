"""Pruebas unitarias para la funcionalidad de ampliación de filas y grillas de tablas (Opción B + C)."""
from __future__ import annotations

import fitz
import pytest

from app import operations as ops


def _create_sample_doc_with_table() -> fitz.Document:
    doc = fitz.open()
    p = doc.new_page(width=500, height=600)
    # Tabla: 2 columnas, 3 filas
    # Bounding box general: (50, 50, 450, 200)
    p.draw_rect(fitz.Rect(50, 50, 450, 200), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(50, 100), fitz.Point(450, 100), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(50, 150), fitz.Point(450, 150), color=(0, 0, 0), width=1)
    p.draw_line(fitz.Point(200, 50), fitz.Point(200, 200), color=(0, 0, 0), width=1)

    # Texto de cabecera y filas
    p.insert_text(fitz.Point(60, 80), "Encabezado 1")
    p.insert_text(fitz.Point(210, 80), "Encabezado 2")
    p.insert_text(fitz.Point(60, 130), "Dato Fila 1 Col A")
    p.insert_text(fitz.Point(210, 130), "Dato Fila 1 Col B")
    p.insert_text(fitz.Point(60, 180), "Dato Fila 2 Col A")
    p.insert_text(fitz.Point(210, 180), "Dato Fila 2 Col B")

    # Contenido inferior después de la tabla
    p.insert_text(fitz.Point(60, 350), "Notas y firma inferior")
    p.insert_text(fitz.Point(60, 550), "Pie de página confidencial")

    # Hipervínculo inferior
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(60, 340, 180, 360), "uri": "https://example.com/firma"})
    return doc


def test_detect_tables_on_page():
    doc = _create_sample_doc_with_table()
    page = doc[0]
    tables = ops.detect_tables_on_page(page)

    assert len(tables) >= 1
    t = tables[0]
    assert t["row_count"] >= 2
    assert len(t["rows"]) >= 2
    assert len(t["column_xs"]) >= 2
    assert t["bbox"][1] < t["bbox"][3]

    # Página en blanco sin tablas
    blank_doc = fitz.open()
    blank_page = blank_doc.new_page(width=400, height=400)
    assert ops.detect_tables_on_page(blank_page) == []
    blank_doc.close()
    doc.close()


def test_expand_table_row_shifts_content_down():
    doc = _create_sample_doc_with_table()
    orig_h = doc[0].rect.height
    delta_y = 40.0
    y_split = 150.0  # Fin de la fila 1

    ops.expand_table_row(
        doc,
        0,
        y_split=y_split,
        delta_y=delta_y,
        table_bbox=(50, 50, 450, 200),
        column_xs=[50, 200, 450],
        extend_borders=True,
        expand_page=True,
    )

    assert doc.page_count == 1
    new_page = doc[0]
    # Comprobar que la altura de la página creció en delta_y
    assert abs(new_page.rect.height - (orig_h + delta_y)) < 1e-3

    # Inspeccionar los bloques de texto
    blocks = new_page.get_text("blocks")
    # Texto de cabecera debe seguir en su posición superior
    header_block = [b for b in blocks if "Encabezado 1" in b[4]][0]
    assert header_block[1] < y_split

    # Texto inferior (originalmente en baseline 350, y0=338.2) debe estar desplazado en delta_y (+40) a y0=378.2
    footer_block = [b for b in blocks if "Notas y firma inferior" in b[4]][0]
    assert footer_block[1] > 370.0

    # Texto del pie (originalmente en baseline 550, y0=538.2) debe estar desplazado a y0=578.2
    confidential_block = [b for b in blocks if "Pie de página" in b[4]][0]
    assert confidential_block[1] > 570.0

    # Enlace inferior debe haberse desplazado
    links = new_page.get_links()
    assert len(links) >= 1
    link = links[0]
    assert link["from"].y0 > 370.0
    doc.close()


def test_expand_table_row_without_page_expansion():
    doc = _create_sample_doc_with_table()
    orig_h = doc[0].rect.height
    delta_y = 25.0
    y_split = 100.0

    ops.expand_table_row(
        doc,
        0,
        y_split=y_split,
        delta_y=delta_y,
        table_bbox=(50, 50, 450, 200),
        extend_borders=False,
        expand_page=False,
    )

    # La altura se debe mantener intacta
    assert abs(doc[0].rect.height - orig_h) < 1e-3
    doc.close()


def test_expand_table_row_validation():
    doc = _create_sample_doc_with_table()

    # delta_y <= 0
    with pytest.raises(ValueError, match="El incremento de altura debe ser mayor a 0"):
        ops.expand_table_row(doc, 0, y_split=100.0, delta_y=0)

    # y_split fuera de página
    with pytest.raises(ValueError, match="debe estar dentro de la altura de la página"):
        ops.expand_table_row(doc, 0, y_split=700.0, delta_y=20)

    # page_num fuera de rango
    with pytest.raises(IndexError, match="fuera de rango"):
        ops.expand_table_row(doc, 5, y_split=100.0, delta_y=20)

    doc.close()


def test_expand_table_dialog(qapp):
    from app.dialogs import ExpandTableDialog

    doc = _create_sample_doc_with_table()
    dlg = ExpandTableDialog(doc[0], 0, parent=None)

    assert dlg.combo_table.count() >= 1
    assert dlg.combo_row.count() >= 1
    vals = dlg.get_values()
    assert vals["page_num"] == 0
    assert vals["delta_y"] == 30.0
    assert vals["extend_borders"] is True
    assert vals["expand_page"] is True
    assert vals["y_split"] > 0
    dlg.close()
    doc.close()


def test_expand_table_undo_redo(qapp):
    from app.doc_tab import DocTab

    doc = _create_sample_doc_with_table()
    tab = DocTab("", doc)
    try:
        orig_h = tab.doc[0].rect.height
        # Aplicar operación
        tab.run_edit(
            lambda d: ops.expand_table_row(d, 0, y_split=150.0, delta_y=40.0, extend_borders=True, expand_page=True),
            goto=0,
        )
        assert abs(tab.doc[0].rect.height - (orig_h + 40.0)) < 1e-3

        # Deshacer (Undo / Ctrl+Z)
        tab.undo()
        assert abs(tab.doc[0].rect.height - orig_h) < 1e-3

        # Rehacer (Redo / Ctrl+Y)
        tab.redo()
        assert abs(tab.doc[0].rect.height - (orig_h + 40.0)) < 1e-3
    finally:
        tab.close()

