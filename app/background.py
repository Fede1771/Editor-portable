"""Procesos independientes para PDF; hilos sólo para operaciones externas."""
from __future__ import annotations

import multiprocessing
import os
from PySide6.QtCore import QEventLoop, Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog


class _Worker(QThread):
    finished_with = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.finished_with.emit(self.fn(), None)
        except Exception as exc:
            self.finished_with.emit(None, exc)


def _dialog(parent, text):
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("Un momento…")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    return dlg


def run_blocking(parent, text: str, fn):
    """Office/escáner: no pasar objetos ni funciones que usen PyMuPDF."""
    dlg = _dialog(parent, text)
    loop = QEventLoop()
    box = {}
    worker = _Worker(fn, parent)

    def done(result, error):
        box.update(result=result, error=error)
        loop.quit()

    worker.finished_with.connect(done)
    worker.start()
    loop.exec()
    worker.wait()
    dlg.close()
    if box.get("error") is not None:
        raise box["error"]
    return box.get("result")


def _pdf_process(conn, operation, raw, password, private_mode, args, kwargs):
    """Entrada serializable de spawn: PyMuPDF corre en el hilo principal hijo."""
    from .document_io import open_pdf, serialize_pdf
    from . import privacy
    from .privacy import TempManager
    privacy._SESSION_PRIVATE_MODE = private_mode
    doc = None
    try:
        doc = open_pdf(raw, password)
        if operation == "ocr":
            from .ocr import ocr_document
            result_doc = ocr_document(doc, *args, **kwargs)
            try:
                result = {"pdf": serialize_pdf(result_doc), "ocr": result_doc._editorpdf_ocr_report}
            finally:
                result_doc.close()
        elif operation == "optimize":
            from .optimizer import optimize_document
            result = optimize_document(doc, *args, **kwargs)
        elif operation in {"word", "excel", "images"}:
            from . import conversion
            target = {"word": conversion.convert_to_word, "excel": conversion.convert_to_excel,
                      "images": conversion.convert_to_images}[operation]
            result = target(doc, *args, **kwargs)
        elif operation == "inspect":
            result = {"pid": os.getpid(), "text": "".join(p.get_text() for p in doc),
                      "encryption": doc.metadata.get("encryption"), "private_mode": privacy.is_private_mode()}
        else:
            raise ValueError("Trabajo PDF desconocido.")
        packet = (result, None)
    except Exception as exc:
        packet = (None, f"{type(exc).__name__}: {exc}")
    finally:
        if doc is not None:
            doc.close()
        TempManager.cleanup_all()
        try:
            conn.send(packet)
        finally:
            conn.close()


def run_pdf_job(parent, text: str, operation: str, doc, *args, **kwargs):
    """Enviar bytes cifrados y parámetros; nunca closures ni objetos Qt."""
    from .document_io import open_pdf, serialize_pdf
    raw = serialize_pdf(doc)
    password = getattr(doc, "_editorpdf_password", None)
    from .privacy import is_private_mode
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_pdf_process, args=(send, operation, raw, password, is_private_mode(), args, kwargs))
    dlg = _dialog(parent, text)
    loop = QEventLoop()
    box = {}
    receiver = _Worker(lambda: receive.recv(), parent)

    def received(packet, error):
        if error is not None:
            box["error"] = "El proceso PDF terminó sin devolver un resultado completo."
        else:
            box["result"], box["error"] = packet
        loop.quit()

    try:
        process.start()
        send.close()
        # El hilo sólo recibe bytes; no toca Document ni la GUI. Un PDF grande no bloquea recv en Qt.
        receiver.finished_with.connect(received)
        receiver.start()
        loop.exec()
        if box.get("error"):
            raise RuntimeError(box["error"])
        result = box.get("result")
        if operation == "ocr":
            output = open_pdf(result["pdf"], password)
            output._editorpdf_ocr_report = result["ocr"]
            return output
        return result
    finally:
        if process.pid is not None:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()
        receiver.wait()
        receive.close()
        send.close()
        dlg.close()
