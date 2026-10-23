"""Pruebas del Grupo 6: Privacidad, limpieza de temporales, modo privado, portapapeles y perfil LibreOffice.
Cubre: H26, H27, H46, H47.
"""
from __future__ import annotations

import os
import subprocess
import pymupdf as fitz
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from app import creation, privacy
from app.doc_tab import DocTab, _DocSnapshot
from app.privacy import TempManager, set_private_mode
from app.viewer import PdfView


# ---------------------------------------------------------------------------
# H26: TempManager conserva registros si falla el borrado y aísla por PID
# ---------------------------------------------------------------------------
def test_h26_temp_manager_keeps_locked_file_registered_and_accurate_count(tmp_path, monkeypatch):
    """H26: Si un temporal no puede eliminarse (p. ej. archivo bloqueado), debe permanecer registrado y no contarse como eliminado."""
    fd, locked_path = TempManager.create_temp_file(prefix="editorpdf_lock_", suffix=".tmp")
    os.write(fd, b"LOCKED_DATA")
    os.close(fd)

    fd2, free_path = TempManager.create_temp_file(prefix="editorpdf_free_", suffix=".tmp")
    os.write(fd2, b"FREE_DATA")
    os.close(fd2)

    orig_remove = os.remove

    def guarded_remove(p):
        if os.path.abspath(p) == os.path.abspath(locked_path):
            raise PermissionError("Archivo en uso por otro proceso")
        return orig_remove(p)

    monkeypatch.setattr(os, "remove", guarded_remove)

    cleaned = TempManager.cleanup_all()
    # free_path sí se eliminó; locked_path falló y sigue existiendo
    assert not os.path.exists(free_path)
    assert os.path.exists(locked_path)
    # locked_path debe seguir en _REGISTERED_TEMP_PATHS para reintento posterior
    assert os.path.abspath(locked_path) in privacy._REGISTERED_TEMP_PATHS

    # Al liberarse el bloqueo, el siguiente cleanup_all lo limpia
    monkeypatch.setattr(os, "remove", orig_remove)
    cleaned2 = TempManager.cleanup_all()
    assert cleaned2 >= 1
    assert not os.path.exists(locked_path)
    assert os.path.abspath(locked_path) not in privacy._REGISTERED_TEMP_PATHS


def test_h26_sweep_orphaned_temps_skips_active_pid(tmp_path, monkeypatch):
    """H26: sweep_orphaned_temps no debe borrar temporales pertenecientes a un PID activo."""
    monkeypatch.setattr(privacy.tempfile, "gettempdir", lambda: str(tmp_path))
    import json, time
    root = tmp_path / "EditorPDFPortable"
    root.mkdir()
    active_dir = root / f"editorpdf_p{os.getpid()}_active"
    active_dir.mkdir()
    active_file = active_dir / "work.tmp"
    active_file.write_bytes(b"ACTIVE_WORK")

    dead_dir = root / "editorpdf_p99999999_dead"
    dead_dir.mkdir()
    (dead_dir / "old.tmp").write_bytes(b"ORPHAN_WORK")
    for folder, pid in ((active_dir, os.getpid()), (dead_dir, 99999999)):
        (root / (folder.name + ".owner.json")).write_text(json.dumps({
            "app": privacy._OWNER_TAG, "pid": pid, "created": time.time() - 90000,
        }))
    unowned = root / "editorpdf_p99999999_not_ours"
    unowned.mkdir()

    swept = TempManager.sweep_orphaned_temps()
    assert swept >= 1
    assert not dead_dir.exists()
    assert active_dir.exists()
    assert active_file.read_bytes() == b"ACTIVE_WORK"
    assert unowned.exists(), "No borrar carpetas desconocidas por su nombre"


# ---------------------------------------------------------------------------
# H27: Perfil LibreOffice temporal y aislado fuera de DATA_DIR
# ---------------------------------------------------------------------------
def test_h27_office_conversion_uses_isolated_temp_profile_not_data_dir(tmp_path, monkeypatch):
    """H27: office_to_pdf_file debe usar un perfil temporal aislado en vez de DATA_DIR/lo_profile."""
    captured_cmds: list[list[str]] = []

    monkeypatch.setattr(creation, "find_soffice", lambda: "C:/fake/soffice.exe")

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(list(cmd))
        # Simular creación del PDF de salida en --outdir
        out_idx = cmd.index("--outdir") + 1
        out_dir = cmd[out_idx]
        src_path = cmd[-1]
        out_pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(src_path))[0] + ".pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(out_pdf)
        doc.close()
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(creation.subprocess, "run", fake_run)

    dummy_docx = tmp_path / "documento.docx"
    dummy_docx.write_bytes(b"DUMMY")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    res_pdf = creation.office_to_pdf_file(str(dummy_docx), str(out_dir))
    assert os.path.isfile(res_pdf)
    assert len(captured_cmds) == 1

    env_args = [a for a in captured_cmds[0] if a.startswith("-env:UserInstallation=")]
    assert len(env_args) == 1
    profile_uri = env_args[0].split("=", 1)[1]
    # No debe apuntar a DATA_DIR/lo_profile
    assert "lo_profile" not in profile_uri or creation.DATA_DIR.replace("\\", "/") not in profile_uri


# ---------------------------------------------------------------------------
# H46: Transición a modo privado migra snapshots de disco a RAM y los borra
# ---------------------------------------------------------------------------
def test_h46_enabling_private_mode_migrates_disk_snapshots_to_ram(monkeypatch):
    """H46: Si existen snapshots en disco y el usuario activa modo privado, deben migrarse a RAM y borrarse del disco."""
    set_private_mode(False)
    monkeypatch.setattr(_DocSnapshot, "DISK_THRESHOLD", 64)

    payload = b"%PDF-1.7 SECRET_SNAPSHOT_PAYLOAD " + (b"X" * 200)
    snap = _DocSnapshot(payload)
    disk_path = snap._temp_path
    assert disk_path is not None and os.path.isfile(disk_path)

    # Activar modo privado: debe migrar el snapshot existente a RAM y limpiar el archivo en disco
    set_private_mode(True)
    assert snap._temp_path is None
    assert not os.path.exists(disk_path)
    assert snap.get_bytes() == payload


# ---------------------------------------------------------------------------
# H47: Seleccionar texto no escribe el portapapeles; copia explícita sí y se limpia si es propia
# ---------------------------------------------------------------------------
def test_h47_selection_does_not_overwrite_clipboard_and_cleanup_respects_external_clipboard(qapp):
    """H47: Seleccionar texto (doble clic / Ctrl+A) no debe alterar el portapapeles sin orden explícita."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 60), "CLIPBOARD_SECRET_WORD", fontsize=12)

    view = PdfView(doc)
    view.resize(600, 400)
    view.set_zoom(1.0)

    cb = QApplication.clipboard()
    cb.setText("EXTERNAL_USER_CLIPBOARD")

    # Simular Ctrl+A (Seleccionar todo)
    ev_select_all = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_A, Qt.ControlModifier)
    view.keyPressEvent(ev_select_all)
    assert "CLIPBOARD_SECRET_WORD" in view._selected_text
    # El portapapeles NO debe haber cambiado por la mera selección
    assert cb.text() == "EXTERNAL_USER_CLIPBOARD"

    # Ahora copia explícita (Ctrl+C)
    ev_copy = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
    view.keyPressEvent(ev_copy)
    assert cb.text() == "CLIPBOARD_SECRET_WORD"

    # Si otra aplicación escribe algo nuevo en el portapapeles, nuestra limpieza NO debe borrarlo
    cb.setText("NEW_FROM_OTHER_APP")
    TempManager.cleanup_all()
    assert cb.text() == "NEW_FROM_OTHER_APP"

    # Pero si el portapapeles aún contiene lo que copiamos desde la app, cleanup_all lo limpia
    view._copy_selection()
    assert cb.text() == "CLIPBOARD_SECRET_WORD"
    TempManager.cleanup_all()
    assert cb.text() == ""
    doc.close()
