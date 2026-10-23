"""Ejecuta una función lenta en un hilo mostrando un diálogo de espera (la ventana no se congela)."""
from __future__ import annotations

from typing import Any
import pymupdf as fitz
from PySide6.QtCore import QEventLoop, Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog


def _extract_closure_docs(fn) -> list[tuple[Any, fitz.Document, bytes, str | None]]:
    """Detecta objetos fitz.Document capturados en el closure de `fn` y los serializa en el hilo GUI (H05)."""
    captured: list[tuple[Any, fitz.Document, bytes, str | None]] = []
    cells = getattr(fn, "__closure__", None) or ()
    for cell in cells:
        try:
            val = cell.cell_contents
        except ValueError:
            continue
        if isinstance(val, fitz.Document) and not val.is_closed:
            pwd = getattr(val, "_editorpdf_password", None)
            try:
                raw = val.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP) if pwd else val.tobytes()
            except Exception:
                raw = val.tobytes()
            captured.append((cell, val, raw, pwd))
    return captured


class _Worker(QThread):
    finished_with = Signal(object, object)

    def __init__(self, fn, captured_docs: list[tuple[Any, fitz.Document, bytes, str | None]], parent=None):
        super().__init__(parent)
        self._fn = fn
        self._captured_docs = captured_docs

    def run(self):
        worker_docs: list[tuple[Any, fitz.Document, fitz.Document]] = []
        try:
            # Abrir instancias independientes de fitz.Document exclusivas del hilo trabajador (H05)
            for cell, orig_doc, raw, pwd in self._captured_docs:
                wdoc = fitz.open("pdf", raw)
                if pwd and wdoc.needs_pass:
                    wdoc.authenticate(pwd)
                cell.cell_contents = wdoc
                worker_docs.append((cell, orig_doc, wdoc))

            res = self._fn()
            # Si el trabajador devuelve un fitz.Document nuevo, serializarlo para reabrirlo en el hilo GUI
            if isinstance(res, fitz.Document) and not res.is_closed:
                res_bytes = res.tobytes()
                res.close()
                self.finished_with.emit(("__fitz_doc_bytes__", res_bytes), None)
            else:
                self.finished_with.emit(res, None)
        except Exception as exc:  # noqa: BLE001
            self.finished_with.emit(None, exc)
        finally:
            for cell, orig_doc, wdoc in worker_docs:
                try:
                    cell.cell_contents = orig_doc
                except Exception:
                    pass
                try:
                    if not wdoc.is_closed:
                        wdoc.close()
                except Exception:
                    pass


def run_blocking(parent, text: str, fn):
    """Ejecuta `fn()` en segundo plano aislando cualquier `fitz.Document` capturado para evitar acceso concurrente (H05)."""
    captured_docs = _extract_closure_docs(fn)
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("Un momento…")
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    loop = QEventLoop()
    box: dict = {}
    worker = _Worker(fn, captured_docs, parent)

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
    res = box.get("result")
    if isinstance(res, tuple) and len(res) == 2 and res[0] == "__fitz_doc_bytes__":
        return fitz.open("pdf", res[1])
    return res
