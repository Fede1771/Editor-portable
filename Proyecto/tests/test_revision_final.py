"""Reproducciones de R01-R13 y O01: comprobar datos persistidos y rutas de GUI."""
from __future__ import annotations

import os
import hashlib
import pymupdf as fitz
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from app import forms, security, optimizer, operations, ocr, background, privacy
from app import content_ops as content
from app.document_io import serialize_pdf, open_pdf, clone_pdf
from app.doc_tab import DocTab
from app.dialogs import FillFormsDialog
from app.main_window import MainWindow


def document(text="ORIGINAL"):
    d = fitz.open()
    d.new_page(width=400, height=300).insert_text((30, 50), text)
    return d


def add_field(doc, name="field", kind=fitz.PDF_WIDGET_TYPE_TEXT, value="PUBLIC", flags=0, choices=None):
    p = doc[0]
    w = fitz.Widget()
    w.field_name, w.field_type, w.field_value = name, kind, value
    w.field_flags = flags
    if choices:
        w.choice_values = choices
    y = 80 + sum(1 for _ in p.widgets()) * 60
    w.rect = fitz.Rect(30, y, 250, y + 40)
    return p.add_widget(w).xref


def dispose(win):
    while win.tabs.count():
        tab = win.tabs.widget(0)
        tab.modified = False
        win.close_tab(0)
    win.deleteLater()


@pytest.mark.parametrize("password", ["", "user-password"])
def test_r04_owner_and_user_encryption_survives_undo_exports(tmp_path, qapp, password):
    d = document("SECRET")
    raw = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password,
                    owner_pw="owner-password", permissions=fitz.PDF_PERM_PRINT)
    d.close()
    d = open_pdf(raw, password)
    method, permissions = d.metadata["encryption"], d.permissions
    tab = DocTab("", d)
    tab.run_edit(lambda doc: operations.rotate_pages(doc, [0], 90))
    tab.undo()
    tab.redo()
    tab.undo()
    saved = tmp_path / "normal.pdf"
    tab.save(str(saved))
    exports = [saved, tmp_path / "optimized.pdf", tmp_path / "anonymous.pdf", tmp_path / "extracted.pdf"]
    optimizer.optimize_document(tab.doc, str(exports[1]), compress_images=False)
    security.create_sanitized_copy(tab.doc, str(exports[2]))
    operations.extract_pages(tab.doc, [0], str(exports[3]))
    exports += [tmp_path / "split" / "part_parte01.pdf"]
    exports[-1].parent.mkdir()
    operations.split_every(tab.doc, 1, str(exports[-1].parent), "part")
    for path in exports:
        with open_pdf(path.read_bytes(), password) as reopened:
            assert reopened.metadata["encryption"] == method
            assert reopened.permissions == permissions
            assert "SECRET" in reopened[0].get_text()
    tab.close_document()


def test_r01_gui_images_uses_process_job_and_current_unsaved_document(tmp_path, qapp, monkeypatch, no_dialogs):
    win = MainWindow()
    d = document("CURRENT_UNSAVED")
    win._add_tab("", d, modified=True)
    out_dir = tmp_path / "img_out"
    out_dir.mkdir()
    class DummyScope:
        def pages(self, count, selected):
            return list(range(count))
    class DummyDlg:
        scope = DummyScope()
        def exec(self):
            return QDialog.Accepted
        def folder(self):
            return str(out_dir)
        def format(self):
            return "png"
        def dpi(self):
            return 72
    import app.main_window as mw
    monkeypatch.setattr(mw, "ConvertImagesDialog", lambda *a: DummyDlg())
    monkeypatch.setattr(mw, "run_blocking", lambda *a, **k: pytest.fail("PDF enviado al hilo"))
    win.export_to_images()
    exported = list(out_dir.glob("*.png"))
    assert len(exported) == 1
    assert "CURRENT_UNSAVED" in d[0].get_text()
    dispose(win)


def test_r01_child_error_is_reported_and_original_survives(qapp):
    d = document()
    with pytest.raises(RuntimeError, match="desconocido"):
        background.run_pdf_job(None, "Prueba", "unknown", d)
    assert "ORIGINAL" in d[0].get_text()
    d.close()


def test_r02_render_budget_keeps_visible_marks_at_the_edit_coordinates(qapp, monkeypatch):
    import app.viewer as viewer
    monkeypatch.setattr(viewer, "MAX_RENDER_PIXELS", 20000)
    d = fitz.open()
    p = d.new_page(width=200, height=200)
    p.draw_rect(fitz.Rect(100, 100, 150, 150), fill=(1, 0, 0), color=None)
    view = viewer.PdfView(d)
    view.resize(500, 500)
    view.show()
    view.set_zoom(2.0)
    qapp.processEvents()
    point = view._map_point(0, fitz.Point(125, 125)) + view._page_rects[0].topLeft()
    pixel = view.viewport().grab().toImage().pixelColor(round(point.x()), round(point.y()))
    assert pixel.red() > 220 and pixel.green() < 30
    view.close()
    d.close()


@pytest.mark.parametrize("word", ["/JavaScript", "/JS", "/Launch"])
def test_r03_literal_tokens_do_not_remove_attachments(tmp_path, word):
    d = document()
    data = b"IMPORTANT_ATTACHMENT"
    d.embfile_add("notes.txt", data, filename="notes.txt", desc=f"Manual sobre {word}")
    assert not security.scan_document_security(d)["has_threats"]
    # Con una acción real, eliminar sólo la acción, no el árbol de anexos.
    d.xref_set_key(d.pdf_catalog(), "Names/JavaScript", "<< /Names [(entry) << /S /JavaScript /JS (void 0) >>] >>")
    out = tmp_path / "safe.pdf"
    security.create_sanitized_copy(d, str(out))
    with fitz.open(str(out)) as result:
        assert result.embfile_count() == 1
        assert hashlib.sha256(result.embfile_get(0)).digest() == hashlib.sha256(data).digest()
        assert not security.scan_document_security(result)["has_threats"]
    d.close()


@pytest.mark.parametrize("inherited", [False, True])
def test_r05_redaction_removes_default_values_and_inherited_secrets(tmp_path, inherited):
    d = document()
    xref = add_field(d)
    owner = xref
    if inherited:
        owner = d.get_new_xref()
        d.update_object(owner, f"<< /FT /Tx /T (parent) /Kids [{xref} 0 R] >>")
        d.xref_set_key(xref, "Parent", f"{owner} 0 R")
        d.xref_set_key(d.pdf_catalog(), "AcroForm/Fields", f"[{owner} 0 R]")
    d.xref_set_key(owner, "DV", fitz.get_pdf_str("HIDDEN_SECRET"))
    assert content.redact_search_phrase(d, "HIDDEN_SECRET") > 0
    raw = d.tobytes(garbage=4)
    with fitz.open("pdf", raw) as result:
        assert not list(result[0].widgets())
        assert all("HIDDEN_SECRET" not in result.xref_object(x) for x in range(1, result.xref_length()))
    d.close()


def test_r06_unicode_multiselect_roundtrip_without_changes(qapp):
    choices = ["Español", "日本語", "a(b)\\c", "Other"]
    d = document()
    x = add_field(d, kind=fitz.PDF_WIDGET_TYPE_LISTBOX, flags=1 << 21, choices=choices, value="Other")
    selected = choices[:3]
    d.xref_set_key(x, "V", "[" + " ".join(fitz.get_pdf_str(t) for t in selected) + "]")
    d.xref_set_key(x, "I", "[0 1 2]")
    dlg = FillFormsDialog(forms.get_form_fields(d))
    assert dlg.values()["field"] == selected
    forms.update_form_fields(d, dlg.values())
    with fitz.open("pdf", d.tobytes()) as result:
        assert forms.get_form_fields(result)[0]["value"] == selected
    dlg.deleteLater()
    d.close()


@pytest.mark.parametrize("editable,value", [(True, "CUSTOM_VALUE"), (False, ""), (False, "LEGACY_VALUE")])
def test_r07_combo_noop_preserves_original_value(qapp, editable, value):
    d = document()
    add_field(d, kind=fitz.PDF_WIDGET_TYPE_COMBOBOX, flags=(1 << 18) if editable else 0,
              choices=["A", "B"], value=value)
    dlg = FillFormsDialog(forms.get_form_fields(d))
    assert dlg.values()["field"] == value
    dlg.deleteLater()
    d.close()


@pytest.mark.parametrize("alpha", [0, 64, 128, 192, 255])
def test_r08_downscale_preserves_partial_alpha_colors(tmp_path, alpha):
    from PySide6.QtCore import QByteArray, QBuffer
    im = QImage(512, 512, QImage.Format_RGBA8888)
    im.fill(QColor(200, 100, 50, alpha))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    im.save(buf, "PNG")
    d = fitz.open()
    p = d.new_page(width=200, height=200)
    p.insert_image(p.rect, stream=bytes(ba))
    before = p.get_pixmap().pixel(100, 100)
    path = tmp_path / "scaled.pdf"
    optimizer.optimize_document(d, str(path), max_dim=64)
    with fitz.open(str(path)) as result:
        after = result[0].get_pixmap().pixel(100, 100)
        assert max(abs(a - b) for a, b in zip(before, after)) < 6
        assert result[0].get_images()[0][2] <= 64
    d.close()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_r09_text_edit_near_edge_of_rotated_page(rotation):
    d = fitz.open()
    p = d.new_page(width=600, height=200)
    p.insert_text((450, 100), "ORIGINAL")
    p.set_rotation(rotation)
    content.replace_text_block(d, 0, p.search_for("ORIGINAL")[0], "NEW", autofit=False)
    assert "NEW" in p.get_text() and "ORIGINAL" not in p.get_text()
    d.close()


def test_r10_ocr_failure_preserves_searchable_original_and_reports_failure(monkeypatch):
    d = document("SEARCHABLE_ORIGINAL")
    monkeypatch.setattr(fitz.Pixmap, "pdfocr_tobytes", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("OCR failed")))
    result = ocr.ocr_document(d, language="eng", dpi=72)
    assert result._editorpdf_ocr_report["status"] == "failed"
    assert result._editorpdf_ocr_report["failed"][0]["page"] == 1
    assert "SEARCHABLE_ORIGINAL" in result[0].get_text()
    result.close()
    d.close()


def test_r11_redaction_failure_does_not_show_success(qapp, monkeypatch, no_dialogs):
    import app.main_window as mw
    win = MainWindow()
    win._add_tab("", document())
    class RedactDialog:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.Accepted
        def phrase(self): return "SECRET"
        def fill_color(self): return (0, 0, 0)
    monkeypatch.setattr(mw, "FindRedactDialog", RedactDialog)
    monkeypatch.setattr(win, "_scoped_pages", lambda *a: [0])
    monkeypatch.setattr(content, "redact_search_phrase", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("failed")))
    win.find_and_redact()
    assert not any(kind == "information" for kind, text in no_dialogs[0])
    assert not win.current_tab().modified
    dispose(win)


def test_r13_xfa_requires_explicit_removal_and_keeps_other_data(tmp_path):
    d = document()
    add_field(d)
    x = d.get_new_xref()
    d.update_object(x, "<< >>")
    d.update_stream(x, b'<template><script contentType="application/x-javascript">void 0;</script></template>')
    d.xref_set_key(d.pdf_catalog(), "AcroForm/XFA", f"{x} 0 R")
    d.embfile_add("notes.txt", b"IMPORTANT")
    assert security.scan_document_security(d)["has_xfa"]
    with pytest.raises(security.UnsupportedActiveContentError):
        security.create_sanitized_copy(d, str(tmp_path / "blocked.pdf"))
    assert not (tmp_path / "blocked.pdf").exists()
    out = tmp_path / "approved.pdf"
    security.create_sanitized_copy(d, str(out), remove_xfa=True)
    with fitz.open(str(out)) as result:
        assert not security.has_xfa(result)
        assert result.embfile_count() == 1
        assert b"application/x-javascript" not in result.tobytes(garbage=4)
    assert security.has_xfa(d)
    d.close()


@pytest.mark.parametrize("kind", ["Sound", "Movie", "Rendition", "JavaScript", "Launch"])
def test_r13_scan_and_clean_agree_on_active_actions(kind):
    d = document()
    a = d[0].add_rect_annot(fitz.Rect(20, 20, 40, 40))
    d.xref_set_key(a.xref, "A", f"<< /S /{kind} >>")
    assert security.scan_document_security(d)["has_threats"]
    assert security.sanitize_document(d) > 0
    assert not security.scan_document_security(d)["has_threats"]
    d.close()


def test_o01_direct_rollback_restores_selection_indices_and_appearances(monkeypatch):
    d = document()
    x = add_field(d, name="first", kind=fitz.PDF_WIDGET_TYPE_LISTBOX, flags=1 << 21,
                  choices=["A", "B", "C"], value="A")
    d.xref_set_key(x, "V", "[(A)(B)]")
    d.xref_set_key(x, "I", "[0 1]")
    add_field(d, name="second")
    before = {k: d.xref_get_key(x, k) for k in ("V", "I", "AP")}
    update = fitz.Widget.update
    calls = [0]
    def fail_second(w):
        calls[0] += 1
        if calls[0] == 2: raise RuntimeError("second failed")
        return update(w)
    monkeypatch.setattr(fitz.Widget, "update", fail_second)
    with pytest.raises(RuntimeError):
        forms.update_form_fields(d, {"first": ["B", "C"], "second": "NEW"})
    assert {k: d.xref_get_key(x, k) for k in before} == before
    assert forms.get_form_fields(d)[0]["value"] == ["A", "B"]
    raw = d.tobytes(garbage=0, deflate=False)
    assert b"NEW" not in raw
    d.close()


def test_r07_choice_display_labels_do_not_replace_export_values(qapp):
    d = document()
    x = add_field(d, kind=fitz.PDF_WIDGET_TYPE_COMBOBOX, choices=["AR", "UY"], value="UY")
    d.xref_set_key(x, "Opt", "[[(AR)(Argentina)][(UY)(Uruguay)]]")
    dlg = FillFormsDialog(forms.get_form_fields(d))
    assert dlg.widgets_map["field"][1].currentText() == "Uruguay"
    assert dlg.values()["field"] == "UY"
    dlg.deleteLater()
    d.close()


def test_r12_failure_cleans_isolated_disk_temporary(monkeypatch, tmp_path):
    monkeypatch.setattr(privacy.tempfile, "tempdir", str(tmp_path))
    privacy._SESSION_PRIVATE_MODE = True
    temp_p = privacy.TempManager.create_temp_file(suffix=".tmp", content=b"test")
    assert os.path.dirname(temp_p) == str(tmp_path / "EditorPDFPortable")
    assert os.path.isfile(temp_p + ".owner.json")
    privacy.TempManager.cleanup_all()
    assert not os.path.exists(temp_p)
    assert not os.path.exists(temp_p + ".owner.json")


def test_r12_private_mode_is_passed_to_child(qapp):
    privacy._SESSION_PRIVATE_MODE = True
    d = document()
    result = background.run_pdf_job(None, "Prueba", "inspect", d)
    assert result["private_mode"] is True
    d.close()


def test_r10_gui_does_not_add_false_searchable_ocr_tab(qapp, monkeypatch, no_dialogs):
    import app.main_window as mw
    win = MainWindow()
    win._add_tab("", document())
    class OcrDialog:
        def __init__(self, *a): pass
        def exec(self): return QDialog.Accepted
        def language(self): return "eng"
        def dpi(self): return 72
    result = document()
    result._editorpdf_ocr_report = {"recognized": [], "failed": [{"page": 1, "error": "failed"}], "fallback_language": []}
    monkeypatch.setattr(mw, "OcrDialog", OcrDialog)
    monkeypatch.setattr(win, "_scoped_pages", lambda *a: [0])
    monkeypatch.setattr(mw, "run_pdf_job", lambda *a, **k: result)
    win.run_ocr()
    assert win.tabs.count() == 1 and result.is_closed
    assert not any(kind == "information" for kind, text in no_dialogs[0])
    dispose(win)


def test_mixed_style_edit_requires_an_explicit_choice(qapp, monkeypatch, no_dialogs):
    win = MainWindow()
    d = document()
    win._add_tab("", d)
    monkeypatch.setattr(content, "find_text_block_at", lambda *a, **k: {"has_mixed_styles": True})
    win._on_text_requested(win.current_tab(), 0, fitz.Rect(20, 20, 100, 50))
    assert not win.current_tab().modified
    assert any(kind == "question" for kind, text in no_dialogs[0])
    dispose(win)
