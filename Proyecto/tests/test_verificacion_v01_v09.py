"""Pruebas de regresión y verificación independiente para los hallazgos V01–V09 y O01–O03."""
from __future__ import annotations

import pymupdf as fitz
import pypdf
import pytest
from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFileIconProvider, QScrollArea

import app.attachments as attachments_mod
import app.content_ops as content_ops
import app.conversion as conversion
import app.dialogs as dialogs_mod
import app.doc_tab as doc_tab_mod
import app.forms as forms_mod
import app.ocr as ocr_mod
import app.pdf_objects as pdf_objects
import app.privacy as privacy_mod
import app.security as security_mod
import app.viewer as viewer_mod


def _independent_pdf_contains_tokens(pdf_path_or_bytes: str | bytes, tokens: list[bytes]) -> list[bytes]:
    """Verificador independiente: inspecciona bytes crudos, todos los objetos xref y todos los streams descomprimidos."""
    raw = (
        open(pdf_path_or_bytes, "rb").read()
        if isinstance(pdf_path_or_bytes, str)
        else bytes(pdf_path_or_bytes)
    )
    found: set[bytes] = set()
    for tok in tokens:
        if tok in raw:
            found.add(tok)
    with fitz.open("pdf", raw) as doc:
        for xref in range(1, doc.xref_length()):
            try:
                obj_bytes = (doc.xref_object(xref, compressed=False) or "").encode("utf-8", errors="ignore")
            except Exception:
                obj_bytes = b""
            try:
                stream_bytes = doc.xref_stream(xref) if doc.xref_is_stream(xref) else b""
            except Exception:
                stream_bytes = b""
            combined = obj_bytes + b"\n" + (stream_bytes or b"")
            for tok in tokens:
                if tok in combined:
                    found.add(tok)
    return sorted(found)


# ---------------------------------------------------------------------------
# V01: JavaScript y acciones activas en marcadores (/Outlines) y campos fuera de página
# ---------------------------------------------------------------------------
def test_v01_outline_javascript_and_chained_actions_detected_and_sanitized(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contenido limpio")
    doc.set_toc([[1, "Capitulo 1", 1]])

    cat = doc.pdf_catalog()
    outlines_xref = int(doc.xref_get_key(cat, "Outlines")[1].split()[0])
    first_xref = int(doc.xref_get_key(outlines_xref, "First")[1].split()[0])

    # Acción JavaScript directa en marcador
    act_xref = doc.get_new_xref()
    doc.update_object(act_xref, "<< /S /JavaScript /JS (app.alert('outline-js')) >>")
    doc.xref_set_key(first_xref, "A", f"{act_xref} 0 R")

    # Marcador hermano con acción /URI segura pero continuación /Next activa (/Launch)
    second_xref = doc.get_new_xref()
    next_launch_xref = doc.get_new_xref()
    doc.update_object(next_launch_xref, "<< /S /Launch /F (cmd.exe) >>")
    safe_uri_xref = doc.get_new_xref()
    doc.update_object(safe_uri_xref, f"<< /S /URI /URI (https://example.com) /Next {next_launch_xref} 0 R >>")
    doc.update_object(
        second_xref,
        f"<< /Title (Enlace con Next malicioso) /Parent {outlines_xref} 0 R /Prev {first_xref} 0 R /A {safe_uri_xref} 0 R >>",
    )
    doc.xref_set_key(first_xref, "Next", f"{second_xref} 0 R")
    doc.xref_set_key(outlines_xref, "Last", f"{second_xref} 0 R")

    # Campo en /AcroForm/Fields sin widget en página con /AA JavaScript
    detached_field = doc.get_new_xref()
    doc.update_object(
        detached_field,
        "<< /FT /Tx /T (DetachedField) /AA << /K << /S /JavaScript /JS (app.alert('detached-field-js')) >> >> >>",
    )
    doc.xref_set_key(cat, "AcroForm/Fields", f"[{detached_field} 0 R]")

    report_before = security_mod.scan_document_security(doc)
    assert report_before["has_js"] is True
    assert report_before["has_launch"] is True
    assert report_before["has_threats"] is True

    out_path = str(tmp_path / "sanitized_v01.pdf")
    security_mod.create_sanitized_copy(doc, out_path)
    doc.close()

    with fitz.open(out_path) as clean_doc:
        report_after = security_mod.scan_document_security(clean_doc)
        assert report_after["has_js"] is False
        assert report_after["has_launch"] is False
        assert report_after["has_threats"] is False
        assert [row[:2] for row in clean_doc.get_toc()] == [[1, "Capitulo 1"], [1, "Enlace con Next malicioso"]]

    leaked = _independent_pdf_contains_tokens(
        out_path,
        [b"/JavaScript", b"/JS", b"outline-js", b"detached-field-js", b"/Launch", b"cmd.exe"],
    )
    assert leaked == []


# ---------------------------------------------------------------------------
# V02: Redacción por búsqueda en /RV (string/stream), /RC (string/stream), entidades, XHTML y XFA
# ---------------------------------------------------------------------------
def test_v02_redact_search_phrase_removes_rv_rc_streams_entities_fragmented_xhtml_and_field_family(tmp_path):
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    p0 = doc[0]
    p1 = doc[1]

    # 1. Widget con /RV en stream y XHTML fragmentado + entidad HTML
    w1 = fitz.Widget()
    w1.field_name = "rich_stream_field"
    w1.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w1.rect = fitz.Rect(50, 50, 220, 80)
    w1.field_value = "PUBLIC"
    p0.add_widget(w1)
    w1_xref = next(iter(p0.widgets())).xref
    rv_stream_xref = doc.get_new_xref()
    doc.update_object(rv_stream_xref, "<< >>")
    doc.update_stream(
        rv_stream_xref,
        b"<body><p>PUBLIC <b>&#83;EC</b><span>RET_RV_STREAM</span></p></body>",
    )
    doc.xref_set_key(w1_xref, "RV", f"{rv_stream_xref} 0 R")

    # 3. Anotación con /RC como stream (agregada antes de manipular Annots crudo)
    annot = p0.add_freetext_annot(fitz.Rect(50, 150, 220, 190), "PUBLIC")
    rc_stream_xref = doc.get_new_xref()
    doc.update_object(rc_stream_xref, "<< >>")
    doc.update_stream(rc_stream_xref, b"<body><p>PUBLIC SECRET_RV_STREAM</p></body>")
    doc.xref_set_key(annot.xref, "RC", f"{rc_stream_xref} 0 R")

    # 2. Familia de campos jerárquica (Parent + 2 widgets hijos en páginas distintas)
    parent_xref = doc.get_new_xref()
    kid0_xref = doc.get_new_xref()
    kid1_xref = doc.get_new_xref()
    doc.update_object(
        parent_xref,
        f"<< /FT /Tx /T (family_field) /V (PUBLIC) /RV (<p>SECRET_RV_STREAM</p>) /Kids [{kid0_xref} 0 R {kid1_xref} 0 R] >>",
    )
    doc.update_object(
        kid0_xref,
        f"<< /Type /Annot /Subtype /Widget /Rect [50 100 200 130] /Parent {parent_xref} 0 R /P {p0.xref} 0 R >>",
    )
    doc.update_object(
        kid1_xref,
        f"<< /Type /Annot /Subtype /Widget /Rect [50 100 200 130] /Parent {parent_xref} 0 R /P {p1.xref} 0 R >>",
    )
    p0_annots = doc.xref_get_key(p0.xref, "Annots")[1]
    inner_annots = p0_annots.strip()[1:-1].strip() if p0_annots.startswith("[") else ""
    doc.xref_set_key(p0.xref, "Annots", f"[{inner_annots} {kid0_xref} 0 R]".strip())
    doc.xref_set_key(p1.xref, "Annots", f"[{kid1_xref} 0 R]")
    af_fields = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/Fields")[1]
    inner_af = af_fields.strip()[1:-1].strip() if af_fields.startswith("[") else ""
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/Fields", f"[{inner_af} {parent_xref} 0 R]".strip())

    count = content_ops.redact_search_phrase(doc, "SECRET_RV_STREAM")
    assert count >= 2

    out_bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    assert _independent_pdf_contains_tokens(out_bytes, [b"SECRET_RV_STREAM", b"family_field"]) == []


def test_v02_redaction_requires_explicit_xfa_handling():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "VISIBLE SECRET_XFA_TOKEN")
    xfa_xref = doc.get_new_xref()
    doc.update_object(xfa_xref, "<< >>")
    doc.update_stream(xfa_xref, b"<xdp><datasets>SECRET_XFA_TOKEN</datasets></xdp>")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/XFA", f"{xfa_xref} 0 R")

    with pytest.raises(security_mod.UnsupportedActiveContentError):
        content_ops.redact_search_phrase(doc, "SECRET_XFA_TOKEN", remove_xfa=False)

    with pytest.raises(security_mod.UnsupportedActiveContentError):
        content_ops.apply_redaction(doc, 0, fitz.Rect(50, 50, 300, 100), remove_xfa=False)

    count = content_ops.redact_search_phrase(doc, "SECRET_XFA_TOKEN", remove_xfa=True)
    assert count >= 1
    out_bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    assert _independent_pdf_contains_tokens(out_bytes, [b"SECRET_XFA_TOKEN"]) == []


# ---------------------------------------------------------------------------
# V03: OCR conserva adjuntos de catálogo, marcadores y enlaces internos
# ---------------------------------------------------------------------------
def test_v03_ocr_preserves_attachments_bookmarks_and_links(monkeypatch):
    doc = fitz.open()
    for i in range(2):
        p = doc.new_page(width=300, height=200)
        p.insert_text((36, 72), f"Page {i + 1} sample text for OCR", fontsize=18)
    doc.embfile_add("attachment.txt", b"ATTACHED_DATA")
    doc.set_toc([[1, "Cap 1", 1], [1, "Cap 2", 2]])
    doc[0].insert_link({
        "kind": fitz.LINK_GOTO,
        "from": fitz.Rect(30, 30, 120, 60),
        "page": 1,
        "to": fitz.Point(36, 72),
    })
    doc[0].insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(30, 80, 120, 110),
        "uri": "https://example.com",
    })

    # Simular motor OCR determinista que devuelve un PDF con texto buscable
    def fake_pdfocr_tobytes(self, language="spa", tessdata=None):
        rec = fitz.open()
        rp = rec.new_page(width=300, height=200)
        rp.insert_text((36, 72), f"OCR text ({language})")
        data = rec.tobytes()
        rec.close()
        return data

    monkeypatch.setattr(fitz.Pixmap, "pdfocr_tobytes", fake_pdfocr_tobytes)

    out = ocr_mod.ocr_document(doc, language="eng", dpi=150)
    try:
        assert out.embfile_names() == ["attachment.txt"]
        assert out.embfile_get("attachment.txt") == b"ATTACHED_DATA"
        assert out.get_toc() == [[1, "Cap 1", 1], [1, "Cap 2", 2]]
        links = out[0].get_links()
        assert any(lnk.get("kind") == fitz.LINK_GOTO and lnk.get("page") == 1 for lnk in links)
        assert any(lnk.get("kind") == fitz.LINK_URI and lnk.get("uri") == "https://example.com" for lnk in links)
    finally:
        out.close()
        doc.close()


def test_v03_ocr_detects_unpreserved_forms_and_annotations():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    w = fitz.Widget()
    w.field_name = "campo_ocr"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(20, 20, 120, 50)
    doc[0].add_widget(w)
    doc[1].add_text_annot((50, 50), "Nota importante")

    info = ocr_mod.pages_with_unpreserved_elements(doc)
    assert info["forms"] == [1]
    assert info["annotations"] == [2]
    doc.close()


# ---------------------------------------------------------------------------
# V04: pypdf actualizado (>=6.21.1) y límites de tamaño/profundidad/elementos en pdf_objects
# ---------------------------------------------------------------------------
def test_v04_pypdf_version_and_pdf_objects_limits():
    parts = [int(x) for x in pypdf.__version__.split(".")[:3]]
    assert tuple(parts) >= (6, 21, 1)

    # Límite de bytes crudos
    oversized = "<<" + (" /A (x)" * (pdf_objects.MAX_OBJECT_BYTES // 4)) + " >>"
    with pytest.raises(pdf_objects.PdfObjectLimitError):
        pdf_objects.parse_pdf_object(oversized)

    # Límite de profundidad de anidamiento
    deep = "[" * (pdf_objects.MAX_OBJECT_DEPTH + 4) + "]" * (pdf_objects.MAX_OBJECT_DEPTH + 4)
    with pytest.raises(pdf_objects.PdfObjectLimitError):
        pdf_objects.parse_pdf_object(deep)

    # Límite de cantidad de elementos
    many = "[" + " ".join("1" for _ in range(pdf_objects.MAX_OBJECT_ELEMENTS + 50)) + "]"
    with pytest.raises(pdf_objects.PdfObjectLimitError):
        pdf_objects.parse_pdf_object(many)


# ---------------------------------------------------------------------------
# V05: Detección de firmas sin widget en página y en /Perms
# ---------------------------------------------------------------------------
def test_v05_signature_detection_covers_acroform_fields_and_perms():
    # 1. Firma en /AcroForm/Fields sin widget en página
    doc1 = fitz.open()
    doc1.new_page()
    sig_val = doc1.get_new_xref()
    doc1.update_object(sig_val, "<< /Type /Sig /Filter /Adobe.PPKLite /ByteRange [0 10 20 30] /Contents <0011> >>")
    sig_field = doc1.get_new_xref()
    doc1.update_object(sig_field, f"<< /FT /Sig /T (DetachedSig) /V {sig_val} 0 R >>")
    doc1.xref_set_key(doc1.pdf_catalog(), "AcroForm/Fields", f"[{sig_field} 0 R]")
    assert list(doc1[0].widgets()) == []
    assert forms_mod.document_has_signatures(doc1) is True
    doc1.close()

    # 2. Firma de certificación / permisos en /Catalog /Perms (/DocMDP o /UR3)
    doc2 = fitz.open()
    doc2.new_page()
    mdp_sig = doc2.get_new_xref()
    doc2.update_object(mdp_sig, "<< /Type /Sig /Filter /Adobe.PPKLite /Contents <abcd> >>")
    doc2.xref_set_key(doc2.pdf_catalog(), "Perms", f"<< /DocMDP {mdp_sig} 0 R >>")
    assert forms_mod.document_has_signatures(doc2) is True
    doc2.close()

    # 3. Campo /FT /Sig vacío (sin firmar) no debe disparar falso positivo
    doc3 = fitz.open()
    p3 = doc3.new_page()
    empty_sig = doc3.get_new_xref()
    doc3.update_object(
        empty_sig,
        f"<< /Type /Annot /Subtype /Widget /FT /Sig /T (UnsignedSig) /Rect [20 20 120 50] /P {p3.xref} 0 R >>",
    )
    doc3.xref_set_key(p3.xref, "Annots", f"[{empty_sig} 0 R]")
    doc3.xref_set_key(doc3.pdf_catalog(), "AcroForm/Fields", f"[{empty_sig} 0 R]")
    assert forms_mod.document_has_signatures(doc3) is False
    assert forms_mod.has_signature_fields(doc3) is True
    doc3.close()


# ---------------------------------------------------------------------------
# V06: AttachmentWidget.reload() no consulta QFileInfo/QFileIconProvider con rutas del PDF
# ---------------------------------------------------------------------------
def test_v06_attachment_widget_does_not_resolve_untrusted_paths_in_icon_provider(qapp, monkeypatch):
    doc = fitz.open()
    doc.new_page()
    unc_name = r"\\198.51.100.10\share\secret.docx"
    win_name = r"C:\Windows\System32\calc.exe"
    ads_name = "reporte.pdf:zone.identifier"
    doc.embfile_add(unc_name, b"UNC_PAYLOAD", filename=unc_name)
    doc.embfile_add(win_name, b"WIN_PAYLOAD", filename=win_name)
    doc.embfile_add(ads_name, b"ADS_PAYLOAD", filename=ads_name)

    icon_fileinfo_calls: list[str] = []
    orig_icon = QFileIconProvider.icon

    def spy_icon(self, arg):
        if isinstance(arg, QFileInfo):
            icon_fileinfo_calls.append(arg.filePath())
        return orig_icon(self, arg)

    monkeypatch.setattr(QFileIconProvider, "icon", spy_icon)

    w = attachments_mod.AttachmentWidget(doc)
    try:
        assert icon_fileinfo_calls == []
        shown = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        assert shown == ["secret.docx", "calc.exe", "reporte.pdf_zone.identifier"]
    finally:
        w.deleteLater()
        qapp.processEvents()
        doc.close()


# ---------------------------------------------------------------------------
# V07: Escritura atómica en _atomic_write_target
# ---------------------------------------------------------------------------
def test_v07_atomic_write_target_preserves_existing_file_on_io_error(tmp_path):
    target = tmp_path / "reporte.dat"
    target.write_bytes(b"EXISTING_VALID_CONTENT")
    before_bytes = target.read_bytes()

    def failing_writer(temp_path):
        with open(temp_path, "wb") as f:
            f.write(b"partial-corrupt")
        raise OSError("disk full while writing")

    with pytest.raises(OSError, match="disk full"):
        conversion._atomic_write_target(str(target), ".dat", failing_writer)

    assert target.read_bytes() == before_bytes
    leftover = [p.name for p in tmp_path.iterdir() if p.name != "reporte.dat"]
    assert leftover == []


# ---------------------------------------------------------------------------
# V08: Miniaturas y renderizado acotados por alto/píxeles y sin bucle infinito ante fallos
# ---------------------------------------------------------------------------
def test_v08_thumbnail_bounds_tall_page_and_does_not_retry_failed_page_infinitely(qapp, monkeypatch):
    tall_doc = fitz.open()
    tall_doc.new_page(width=10, height=100000)

    requested_dims: list[tuple[int, int]] = []
    orig_get_pixmap = fitz.Page.get_pixmap

    def spy_get_pixmap(self, *args, **kwargs):
        pm = orig_get_pixmap(self, *args, **kwargs)
        requested_dims.append((pm.width, pm.height))
        return pm

    monkeypatch.setattr(fitz.Page, "get_pixmap", spy_get_pixmap)

    tl = doc_tab_mod.ThumbnailList(tall_doc)
    tl._fill_batch()
    assert requested_dims
    w, h = requested_dims[-1]
    assert w <= doc_tab_mod.THUMB_W + 2
    assert h <= doc_tab_mod.THUMB_H + 2
    assert w * h <= viewer_mod.MAX_THUMB_PIXELS * 2
    tl.deleteLater()
    qapp.processEvents()
    tall_doc.close()

    # Verificar que una página que lanza excepción no provoque reintentos infinitos
    fail_doc = fitz.open()
    fail_doc.new_page(width=200, height=200)
    fail_doc.new_page(width=200, height=200)
    calls = {"p0": 0, "p1": 0}

    def flaky_get_pixmap(self, *args, **kwargs):
        if self.number == 0:
            calls["p0"] += 1
            raise RuntimeError("renderboom")
        calls["p1"] += 1
        return orig_get_pixmap(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_pixmap", flaky_get_pixmap)

    tl2 = doc_tab_mod.ThumbnailList(fail_doc)
    for _ in range(5):
        tl2._fill_batch()
    assert calls["p0"] == 1
    assert calls["p1"] == 1
    assert not tl2._timer.isActive()
    tl2.deleteLater()
    qapp.processEvents()
    fail_doc.close()


# ---------------------------------------------------------------------------
# V09: ListBox multiselección persiste en el campo canónico (Parent) para lectores externos (pypdf)
# ---------------------------------------------------------------------------
def test_v09_multiselect_listbox_updates_canonical_parent_for_pypdf(tmp_path):
    doc = fitz.open()
    p = doc.new_page()
    w = fitz.Widget()
    w.field_name = "multi"
    w.field_type = fitz.PDF_WIDGET_TYPE_LISTBOX
    w.field_flags = getattr(fitz, "PDF_CH_FIELD_IS_MULTI_SELECT", 1 << 21)
    w.rect = fitz.Rect(50, 50, 200, 130)
    w.choice_values = ["A", "B", "C"]
    w.field_value = "A"
    p.add_widget(w)

    updated = forms_mod.update_form_fields(doc, {"multi": ["A", "C"]})
    assert updated == 1

    out_path = tmp_path / "multiselect_v09.pdf"
    doc.save(str(out_path))
    doc.close()

    # Verificación con nuestro lector
    with fitz.open(str(out_path)) as reopened:
        fields = forms_mod.get_form_fields(reopened)
        assert fields[0]["value"] == ["A", "C"]

        # Verificación con lector externo independiente (pypdf)
        reader = pypdf.PdfReader(str(out_path))
        pypdf_fields = reader.get_fields()
        assert list(pypdf_fields["multi"]["/V"]) == ["A", "C"]
        raw_field = reader.trailer["/Root"]["/AcroForm"]["/Fields"][0].get_object()
        assert [int(x) for x in raw_field["/I"]] == [0, 2]

        # También verificar limpieza a lista vacía []
        forms_mod.update_form_fields(reopened, {"multi": []})
        out_empty = tmp_path / "multiselect_empty.pdf"
        reopened.save(str(out_empty))

    reader_empty = pypdf.PdfReader(str(out_empty))
    assert list(reader_empty.get_fields()["multi"].get("/V", [])) == []


# ---------------------------------------------------------------------------
# O01, O02, O03: Observaciones menores
# ---------------------------------------------------------------------------
def test_o01_accepting_fill_forms_dialog_unchanged_does_not_dirty_checkbox(qapp):
    doc = fitz.open()
    p = doc.new_page()
    w = fitz.Widget()
    w.field_name = "acepto"
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(50, 50, 70, 70)
    w.field_value = "Off"
    p.add_widget(w)

    fields = forms_mod.get_form_fields(doc)
    dlg = dialogs_mod.FillFormsDialog(fields)
    vals = dlg.values()
    try:
        cur_map = {f["name"]: f for f in fields}
        changes = {
            k: v for k, v in vals.items()
            if k in cur_map
            and forms_mod.normalize_field_value(cur_map[k], cur_map[k].get("value"))
            != forms_mod.normalize_field_value(cur_map[k], v)
        }
        assert changes == {}
    finally:
        dlg.deleteLater()
        qapp.processEvents()
        doc.close()


def test_o02_safe_link_dialog_and_viewer_ctrl_c_use_privacy_clipboard(qapp):
    privacy_mod._LAST_APP_CLIPBOARD_TEXT = None
    dlg = security_mod.SafeLinkDialog("https://example.org/privado")
    try:
        dlg._copy_url()
        assert QApplication.clipboard().text() == "https://example.org/privado"
        assert privacy_mod._LAST_APP_CLIPBOARD_TEXT == "https://example.org/privado"
        assert privacy_mod.clear_app_clipboard_if_owned() is True
        assert QApplication.clipboard().text() == ""
    finally:
        dlg.deleteLater()
        qapp.processEvents()

    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "TextoSeleccionadoPrivado")
    view = viewer_mod.PdfView(doc)
    view._selected_text = "TextoSeleccionadoPrivado"
    try:
        ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
        view.keyPressEvent(ev)
        assert QApplication.clipboard().text() == "TextoSeleccionadoPrivado"
        assert privacy_mod._LAST_APP_CLIPBOARD_TEXT == "TextoSeleccionadoPrivado"
        assert privacy_mod.clear_app_clipboard_if_owned() is True
        assert QApplication.clipboard().text() == ""
    finally:
        view._prefetch_timer.stop()
        view.deleteLater()
        qapp.processEvents()
        doc.close()


def test_o03_fill_forms_dialog_uses_scroll_area_and_bounds_height(qapp):
    fields = [
        {
            "name": f"campo_{i}",
            "label": f"Campo {i}",
            "type": "Text",
            "value": f"valor {i}",
            "page": 0,
            "read_only": False,
            "is_signature": False,
        }
        for i in range(60)
    ]
    dlg = dialogs_mod.FillFormsDialog(fields)
    try:
        scroll = dlg.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.widgetResizable() is True
        assert dlg.sizeHint().height() <= 680
        assert dlg.maximumHeight() <= 680
    finally:
        dlg.deleteLater()
        qapp.processEvents()
