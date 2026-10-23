"""Configuración común de las regresiones de auditoría (pytest).

- Preferencias aisladas en un INI temporal (no se toca el Registro ni los recientes reales).
- Directorio temporal propio por sesión de pruebas.
- QApplication en modo offscreen.
"""
from __future__ import annotations

import os
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SESSION_TMP = tempfile.mkdtemp(prefix="editorpdf_pytest_")
os.environ["EDITORPDF_SETTINGS_DIR"] = os.path.join(_SESSION_TMP, "settings")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings("ignore", category=FutureWarning)

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_private_mode():
    from app import privacy
    privacy._SESSION_PRIVATE_MODE = False
    yield
    privacy._SESSION_PRIVATE_MODE = False


@pytest.fixture
def no_dialogs(monkeypatch):
    """Reemplaza QMessageBox / QFileDialog por receptores simulados que registran las llamadas."""
    from PySide6.QtWidgets import QMessageBox
    calls: list[tuple[str, str]] = []

    def _mk(kind, default):
        def _f(*args, **kwargs):
            title = args[1] if len(args) > 1 else ""
            text = args[2] if len(args) > 2 else ""
            calls.append((kind, f"{title}|{text}"))
            return _f.answer
        _f.answer = default
        return _f

    fns = {
        "warning": _mk("warning", QMessageBox.Cancel),
        "question": _mk("question", QMessageBox.No),
        "information": _mk("information", QMessageBox.Ok),
        "critical": _mk("critical", QMessageBox.Ok),
    }
    for name, fn in fns.items():
        monkeypatch.setattr(QMessageBox, name, staticmethod(fn))
    return calls, fns
