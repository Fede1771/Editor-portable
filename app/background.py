"""Ejecuta una función lenta en un hilo mostrando un diálogo de espera (la ventana no se congela)."""
from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog


class _Worker(QThread):
    finished_with = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.finished_with.emit(self._fn(), None)
        except Exception as exc:  # noqa: BLE001
            self.finished_with.emit(None, exc)


def run_blocking(parent, text: str, fn):
    """Ejecuta `fn()` en segundo plano, espera con un diálogo y devuelve su resultado (o relanza el error)."""
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("Un momento…")
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    loop = QEventLoop()
    box: dict = {}
    worker = _Worker(fn, parent)

    def _done(result, error):
        box["result"], box["error"] = result, error
        loop.quit()

    worker.finished_with.connect(_done)
    worker.start()
    loop.exec()
    worker.wait()
    dlg.close()
    if box.get("error") is not None:
        raise box["error"]
    return box.get("result")
