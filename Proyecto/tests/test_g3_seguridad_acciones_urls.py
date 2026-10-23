"""G3 - Seguridad de acciones PDF, enlaces y estado visual post-Undo: H10, H13, H42, H43, H44, N03."""
from __future__ import annotations

import pymupdf as fitz
import pytest


# ------------------------------------------------------------------ H10 acciones PDF
def test_h10_direct_names_javascript_is_detected_and_removed():
    from app.security import scan_document_security, sanitize_document
    doc = fitz.open()
    doc.new_page()
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "Names", "<< /JavaScript << /Names [ (s1) << /S /JavaScript /JS (app.alert(1)) >> ] >> >>")

    sec_before = scan_document_security(doc)
    assert sec_before["has_threats"] is True
    assert sec_before["has_js"] is True

    cleaned = sanitize_document(doc)
    assert cleaned >= 1

    sec_after = scan_document_security(doc)
    assert sec_after["has_threats"] is False
    doc.close()


def test_h10_page_aa_and_annot_aa_and_action_chains_are_detected_and_removed(tmp_path):
    from app.security import scan_document_security, sanitize_document
    doc = fitz.open()
    page = doc.new_page()
    # 1) /AA en página
    doc.xref_set_key(page.xref, "AA", "<< /O << /S /JavaScript /JS (void 0) >> >>")
    # 2) Anotación con /AA y cadena /A -> /Next con /Launch
    annot = page.add_rect_annot(fitz.Rect(20, 20, 80, 80))
    next_xref = doc.get_new_xref()
    doc.update_object(next_xref, "<< /S /Launch /F (cmd.exe) >>")
    doc.xref_set_key(annot.xref, "AA", "<< /E << /S /JavaScript /JS (void 0) >> >>")
    doc.xref_set_key(annot.xref, "A", f"<< /S /URI /URI (https://example.com) /Next {next_xref} 0 R >>")

    sec_before = scan_document_security(doc)
    assert sec_before["has_threats"] is True

    cleaned = sanitize_document(doc)
    assert cleaned >= 2

    out = tmp_path / "limpio.pdf"
    doc.save(str(out), garbage=3, deflate=True)
    doc.close()

    reopened = fitz.open(str(out))
    try:
        sec_after = scan_document_security(reopened)
        assert sec_after["has_threats"] is False, f"Amenazas remanentes: {sec_after}"
    finally:
        reopened.close()


# ------------------------------------------------------------------ H13 y N03 banner + Undo/Redo
def test_n03_undo_after_sanitize_restores_warning_banner_and_button(qapp):
    from app.doc_tab import DocTab
    from app.security import scan_document_security
    doc = fitz.open()
    doc.new_page()
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", "<< /S /JavaScript /JS (void 0) >>")

    tab = DocTab("", doc)
    assert scan_document_security(tab.doc)["has_threats"] is True
    assert not tab.security_banner.isHidden()
    assert not tab.security_banner.btn_sanitize.isHidden()

    tab.sanitize_security()
    assert scan_document_security(tab.doc)["has_threats"] is False
    assert tab.security_banner.btn_sanitize.isHidden()

    tab.undo()
    assert scan_document_security(tab.doc)["has_threats"] is True
    assert not tab.security_banner.isHidden()
    assert not tab.security_banner.btn_sanitize.isHidden(), "El botón de sanitizar siguió oculto tras Undo"
    assert "sanitizado con éxito" not in tab.security_banner.msg_lbl.text()


# ------------------------------------------------------------------ H42 bloqueo de esquemas
@pytest.mark.parametrize("bad_url", [
    "file:///C:/inert.txt",
    "javascript:alert(1)",
    "ms-msdt:/id PCWDiagnostic",
    "customproto://open/item",
    "https:///",
])
def test_h42_prohibited_or_invalid_urls_never_reach_openurl(bad_url, qapp, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from app.security import SafeLinkDialog
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: opened.append(u.toString()) or True))

    dlg = SafeLinkDialog(bad_url, text="Enlace")
    assert not dlg.btn_open.isEnabled(), f"btn_open quedó habilitado para {bad_url!r}"
    dlg._open_url()
    assert opened == [], f"openUrl fue invocado para {bad_url!r}"


# ------------------------------------------------------------------ H43 clasificador de enlaces
def test_h43_url_classifier_catches_empty_host_percent_encoded_exe_and_ipv6():
    from app.security import check_url_safety
    r_empty = check_url_safety("https:///")
    assert r_empty["is_safe"] is False
    assert r_empty["can_open"] is False

    r_pct = check_url_safety("https://example.test/file%2Eexe")
    assert r_pct["is_safe"] is False
    assert any("ejecutable" in w.lower() for w in r_pct["warnings"])

    r_ipv6 = check_url_safety("https://[::1]/login")
    assert r_ipv6["is_safe"] is False
    assert any("ip" in w.lower() for w in r_ipv6["warnings"])

    r_user = check_url_safety("https://banco.com@atacante.test/login")
    assert r_user["is_safe"] is False


# ------------------------------------------------------------------ H44 HTML escapado en QLabel
def test_h44_labels_do_not_interpret_untrusted_html(qapp):
    from PySide6.QtCore import Qt
    from app.security import SafeLinkDialog, SecurityBanner
    payload = "https://example.test/<br><b>DESTINO VERIFICADO</b>"
    dlg = SafeLinkDialog(payload, text="<b>BANCO</b>")
    assert dlg.lbl_dest.textFormat() == Qt.PlainText
    for w_lbl in dlg.warning_labels:
        assert w_lbl.textFormat() == Qt.PlainText

    banner = SecurityBanner()
    banner.show_threats({"threat_details": ["Adjunto <b>FALSO_OK</b>.exe"]})
    assert "&lt;b&gt;FALSO_OK&lt;/b&gt;" in banner.msg_lbl.text()
