"""G1 - Adjuntos: H02, H15, H24, H40, H41.

Ningún lanzamiento externo es real: os.startfile se intercepta y los bytes son inertes.
"""
from __future__ import annotations

import gc
import os

import pymupdf as fitz
import pytest


def _doc_with_embedded(names: list[str]) -> fitz.Document:
    doc = fitz.open()
    doc.new_page()
    for i, n in enumerate(names):
        doc.embfile_add(f"e{i}", b"INERT", filename=n, ufilename=n)
    return doc


@pytest.fixture
def launches(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(os, "startfile", lambda p, *a, **k: calls.append(p), raising=False)
    return calls


# ----------------------------------------------------------------- H02 nombres
@pytest.mark.parametrize("raw", [
    "../victim.txt", "..\\..\\victim.txt", "C:\\Windows\\victim.txt", "C:victim.txt",
    "\\\\server\\share\\victim.txt", "victim.txt:Zone.Identifier", "/etc/victim.txt",
])
def test_h02_safe_local_name_has_no_path_components(raw):
    from app.attachments import safe_local_name
    name = safe_local_name(raw)
    assert name and "/" not in name and "\\" not in name and ":" not in name
    assert name not in (".", "..")


@pytest.mark.parametrize("raw", ["CON", "con.txt", "NUL", "aux.pdf", "COM1.txt", "lpt9", "CONIN$"])
def test_h02_reserved_device_names_are_neutralized(raw):
    from app.attachments import safe_local_name
    name = safe_local_name(raw)
    stem = name.split(".")[0].upper()
    assert stem not in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}


def test_h02_extract_all_never_writes_outside(tmp_path, qapp, monkeypatch, no_dialogs):
    from PySide6.QtWidgets import QFileDialog
    from app.attachments import AttachmentWidget
    outside = tmp_path / "victim.txt"
    outside.write_bytes(b"ORIGINAL")
    target = tmp_path / "out"
    target.mkdir()
    doc = _doc_with_embedded(["../victim.txt", str(outside), "CON.txt", "ok.txt"])
    w = AttachmentWidget(doc)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target)))
    w.extract_all()
    assert outside.read_bytes() == b"ORIGINAL"
    written = sorted(p.name for p in target.iterdir())
    assert len(written) == 4
    for p in target.iterdir():
        assert p.resolve().parent == target.resolve()


# ------------------------------------------------- H40 normalizar antes de clasificar
@pytest.mark.parametrize("fn", [
    "blocked.cmd", "blocked.cmd ", "blocked.cmd.", "blocked.exe.", "blocked.hta. ",
    "documento.url", "documento.docm", "documento.xlsm", "documento.chm", "x.exe::$DATA",
    "desconocido.xyz", "sin_extension",
])
def test_h40_active_or_unknown_types_do_not_reach_shell_silently(fn, qapp, launches, no_dialogs, monkeypatch):
    from app.attachments import AttachmentWidget, get_all_attachments
    calls, fns = no_dialogs
    doc = _doc_with_embedded([fn])
    w = AttachmentWidget(doc)
    monkeypatch.setattr(w, "save_selected", lambda *a, **k: None)
    att = get_all_attachments(doc)[0]
    w._open_attachment(att)
    assert launches == [], f"{fn!r} llegó a os.startfile"
    assert any(k == "warning" for k, _ in calls), f"{fn!r} no produjo advertencia"


def test_h40_passive_type_still_opens(qapp, launches, no_dialogs):
    from app.attachments import AttachmentWidget, get_all_attachments
    doc = _doc_with_embedded(["foto.png"])
    w = AttachmentWidget(doc)
    w._open_attachment(get_all_attachments(doc)[0])
    assert len(launches) == 1 and launches[0].endswith("foto.png")


def test_h40_scanner_uses_canonical_extension():
    from app.security import scan_document_security
    doc = _doc_with_embedded(["malo.exe. "])
    assert scan_document_security(doc)["has_threats"]


# ----------------------------------------------------------------- H41 MOTW
def _read_zone(path: str) -> str | None:
    try:
        with open(path + ":Zone.Identifier", "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def test_h41_extracted_attachment_is_marked_untrusted(tmp_path, qapp, monkeypatch, no_dialogs):
    from PySide6.QtWidgets import QFileDialog
    from app.attachments import AttachmentWidget
    probe = tmp_path / "probe.txt"
    probe.write_text("x")
    try:
        with open(str(probe) + ":Zone.Identifier", "w") as fh:
            fh.write("[ZoneTransfer]\r\nZoneId=3\r\n")
    except OSError:
        pytest.skip("El sistema de archivos no admite flujos alternativos (ADS)")
    doc = _doc_with_embedded(["planilla.xlsx"])
    w = AttachmentWidget(doc)
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target)))
    w.extract_all()
    out = target / "planilla.xlsx"
    zone = _read_zone(str(out))
    assert zone and "ZoneId=3" in zone


def test_h41_container_zone_is_propagated(tmp_path):
    from app.attachments import write_mark_of_the_web, read_zone_id
    src = tmp_path / "descargado.pdf"
    src.write_bytes(b"%PDF")
    try:
        with open(str(src) + ":Zone.Identifier", "w") as fh:
            fh.write("[ZoneTransfer]\r\nZoneId=4\r\n")
    except OSError:
        pytest.skip("Sin soporte ADS")
    assert read_zone_id(str(src)) == 4
    dst = tmp_path / "adjunto.docx"
    dst.write_bytes(b"x")
    assert write_mark_of_the_web(str(dst), source_path=str(src))
    assert read_zone_id(str(dst)) == 4


# ----------------------------------------------------------------- H15 wrappers
def test_h15_annotation_attachment_survives_gc():
    from app.attachments import get_all_attachments, get_attachment_bytes
    doc = fitz.open()
    page = doc.new_page()
    page.add_file_annot(fitz.Point(50, 50), b"ANNOT_DATA", "nota.txt")
    del page
    items = get_all_attachments(doc)
    gc.collect()
    for _ in doc:
        pass
    gc.collect()
    att = [i for i in items if i["source"] == "annot"][0]
    assert get_attachment_bytes(doc, att) == b"ANNOT_DATA"


# ----------------------------------------------------------------- H24 undo
def test_h24_add_and_delete_attachment_are_undoable(tmp_path, qapp, monkeypatch, no_dialogs):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from app.doc_tab import DocTab
    calls, fns = no_dialogs
    src = tmp_path / "a.txt"
    src.write_bytes(b"AAA")
    doc = fitz.open()
    doc.new_page()
    tab = DocTab("", doc)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(src), "")))
    tab.attachments.add_attachment()
    assert tab.doc.embfile_count() == 1
    assert tab.can_undo
    tab.undo()
    assert tab.doc.embfile_count() == 0
    tab.redo()
    assert tab.doc.embfile_count() == 1
    # eliminar también es transacción y descarta redo
    fns["question"].answer = QMessageBox.Yes
    tab.attachments.tree.setCurrentItem(tab.attachments.tree.topLevelItem(0))
    tab.attachments.delete_selected()
    assert tab.doc.embfile_count() == 0
    assert not tab.can_redo
    tab.undo()
    assert tab.doc.embfile_count() == 1
