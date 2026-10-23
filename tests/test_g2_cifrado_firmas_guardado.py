"""G2 - Cifrado, firmas digitales, guardado atómico y copia anónima: H04, H19, H29, H49, N04."""
from __future__ import annotations

import hashlib
import re

import pymupdf as fitz
import pytest


def _make_encrypted_pdf(user_pw: str = "clave_usuario", owner_pw: str = "clave_propietario") -> bytes:
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 70), "CONFIDENCIAL_AES256")
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=user_pw,
        owner_pw=owner_pw,
        permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY,
    )
    doc.close()
    return data


def _make_unsigned_sig_pdf() -> bytes:
    """PDF con campo /FT /Sig vacío (/V null) y /SigFlags 1."""
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_name = "FirmaVacia"
    w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    w.rect = fitz.Rect(50, 50, 200, 100)
    page.add_widget(w)
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/SigFlags", "1")
    data = doc.tobytes()
    doc.close()
    return data


def _make_signed_pdf_bytes() -> bytes:
    """Construye un PDF con un widget Signature cuyo /V apunta a un diccionario de firma con /ByteRange y /Contents."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Notificacion firmada " * 20)
    w = fitz.Widget()
    w.field_name = "Firma1"
    w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    w.rect = fitz.Rect(50, 100, 220, 150)
    page.add_widget(w)
    w_xref = list(page.widgets())[0].xref
    sig_xref = doc.get_new_xref()
    doc.update_object(
        sig_xref,
        "<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
        "/ByteRange [0 300 450 600] /Contents <" + ("ab" * 32) + "> >>",
    )
    doc.xref_set_key(w_xref, "V", f"{sig_xref} 0 R")
    raw = doc.tobytes(garbage=0, deflate=False)
    doc.close()
    return raw


def _byterange_hashes(pdf_bytes: bytes) -> list[str]:
    hashes = []
    for m in re.finditer(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]", pdf_bytes):
        a, b, c, d = (int(x) for x in m.groups())
        seg = pdf_bytes[a : a + b] + pdf_bytes[c : c + d]
        hashes.append(hashlib.sha256(seg).hexdigest())
    return hashes


# ------------------------------------------------------------------ H04 cifrado
def test_h04_save_preserves_aes256_encryption(tmp_path, qapp):
    from app.doc_tab import DocTab
    enc_bytes = _make_encrypted_pdf("mi_clave", "mi_owner")
    src = tmp_path / "protegido.pdf"
    src.write_bytes(enc_bytes)

    doc = fitz.open("pdf", enc_bytes)
    assert doc.needs_pass == 1
    assert doc.authenticate("mi_clave") > 0

    out = tmp_path / "guardado.pdf"
    tab = DocTab(str(out), doc)
    tab.save()

    reopened = fitz.open(str(out))
    try:
        assert reopened.needs_pass == 1, "El archivo guardado perdió la protección por contraseña"
        assert reopened.authenticate("incorrecta") == 0
        assert reopened.authenticate("mi_clave") > 0
        assert "AES" in (reopened.metadata.get("encryption") or "")
        assert "CONFIDENCIAL_AES256" in reopened[0].get_text()
    finally:
        reopened.close()


def test_h04_undo_redo_and_save_preserve_encryption(tmp_path, qapp):
    from app import operations as ops
    from app.doc_tab import DocTab
    enc_bytes = _make_encrypted_pdf("clave123", "owner123")
    doc = fitz.open("pdf", enc_bytes)
    assert doc.authenticate("clave123") > 0

    out = tmp_path / "tras_undo.pdf"
    tab = DocTab(str(out), doc)
    tab.run_edit(lambda d: ops.rotate_pages(d, [0], 90))
    tab.undo()
    tab.redo()
    tab.save()

    reopened = fitz.open(str(out))
    try:
        assert reopened.needs_pass == 1
        assert reopened.authenticate("clave123") > 0
        assert reopened[0].rotation == 90
    finally:
        reopened.close()


# ------------------------------------------------------------------ H29 temporal único
def test_h29_save_does_not_destroy_existing_dot_tmp_file(tmp_path, qapp):
    from app.doc_tab import DocTab
    target = tmp_path / "saved.pdf"
    preexisting_tmp = tmp_path / "saved.pdf.tmp"
    preexisting_tmp.write_bytes(b"ARCHIVO_AJENO_IMPORTANTE")

    doc = fitz.open()
    doc.new_page()
    tab = DocTab(str(target), doc)
    tab.save()

    assert target.exists()
    assert preexisting_tmp.exists(), "saved.pdf.tmp preexistente fue destruido por DocTab.save"
    assert preexisting_tmp.read_bytes() == b"ARCHIVO_AJENO_IMPORTANTE"


# ------------------------------------------------------------------ H19 copia anónima conserva estructura
def test_h19_anonymous_copy_preserves_bookmarks_and_attachments(tmp_path, qapp):
    from app.security import create_sanitized_copy
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), " Capitulo 1")
    p2 = doc.new_page()
    p2.insert_text((50, 50), " Capitulo 2")
    doc.set_toc([[1, "Capitulo 1", 1], [1, "Capitulo 2", 2]])
    doc.embfile_add("anexo.txt", b"DATOS_ANEXO", filename="anexo.txt")
    doc.set_metadata({"author": "SECRET_USER", "title": "Privado"})
    p1 = doc[0]
    p1.add_text_annot((100, 100), "Nota", icon="Note")
    for a in p1.annots():
        info = a.info
        info["title"] = "SECRET_ANNOT_AUTHOR"
        a.set_info(info)

    out = tmp_path / "anonimo.pdf"
    create_sanitized_copy(doc, str(out))
    doc.close()

    res = fitz.open(str(out))
    try:
        assert res.embfile_count() == 1
        assert len(res.get_toc()) == 2
        assert (res.metadata.get("author") or "") == ""
        for a in res[0].annots():
            assert a.info.get("title") != "SECRET_ANNOT_AUTHOR"
    finally:
        res.close()


# ------------------------------------------------------------------ N04 y H49 firmas
def test_n04_empty_signature_field_is_not_reported_as_cryptographic_signature():
    from app.forms import document_has_signatures, has_signature_fields
    raw = _make_unsigned_sig_pdf()
    doc = fitz.open("pdf", raw)
    try:
        assert has_signature_fields(doc) is True
        assert document_has_signatures(doc) is False
    finally:
        doc.close()


def test_h49_signed_document_is_detected_and_unmodified_save_keeps_byterange_bytes(tmp_path, qapp):
    from app.forms import document_has_signatures
    from app.doc_tab import DocTab
    raw = _make_signed_pdf_bytes()
    orig_hashes = _byterange_hashes(raw)
    assert orig_hashes

    doc = fitz.open("pdf", raw)
    assert document_has_signatures(doc) is True

    out = tmp_path / "firmado_guardado.pdf"
    tab = DocTab(str(out), doc)
    assert tab.modified is False
    tab.save()

    saved_bytes = out.read_bytes()
    assert _byterange_hashes(saved_bytes) == orig_hashes


def test_h49_compress_and_sanitized_copy_warn_on_signed_pdf(tmp_path, qapp, monkeypatch, no_dialogs):
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
    from app.dialogs import CompressPdfDialog
    from app.main_window import MainWindow
    calls, fns = no_dialogs
    fns["warning"].answer = QMessageBox.No  # El usuario cancela ante la advertencia de firma
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(CompressPdfDialog, "exec", lambda self: QDialog.Rejected)

    raw = _make_signed_pdf_bytes()
    doc = fitz.open("pdf", raw)
    win = MainWindow()
    win._add_tab(str(tmp_path / "firmado.pdf"), doc)

    calls.clear()
    win.compress_document()
    assert any(k == "warning" and "Firma" in msg for k, msg in calls), "Comprimir no advirtió sobre firma digital"

    calls.clear()
    win.save_sanitized_current()
    assert any(k == "warning" and "Firma" in msg for k, msg in calls), "Copia anónima no advirtió sobre firma digital"
    win.close()
