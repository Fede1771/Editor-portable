"""Motor de OCR integrado (fase 5): convierte páginas escaneadas a PDF con texto buscable."""
from __future__ import annotations

import os
import sys
from typing import Callable, Sequence

import pymupdf as fitz


def _resolve_tessdata_dir() -> str:
    """Resuelve la ruta de tessdata de forma robusta tanto en desarrollo como en ejecutable portable."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, "_MEIPASS", exe_dir)
        candidates.extend([
            os.path.join(meipass, "data", "tessdata"),
            os.path.join(exe_dir, "_internal", "data", "tessdata"),
            os.path.join(exe_dir, "data", "tessdata"),
        ])
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(app_root, "data", "tessdata"))
    for cand in candidates:
        if os.path.isdir(cand):
            return cand
    return candidates[0]


TESSDATA_DIR = _resolve_tessdata_dir()


def get_available_languages() -> dict[str, str]:
    """Retorna los idiomas disponibles en la carpeta local de tessdata."""
    available = {}
    if os.path.isdir(TESSDATA_DIR):
        for f in os.listdir(TESSDATA_DIR):
            if f.endswith(".traineddata"):
                code = f.replace(".traineddata", "")
                name = {
                    "spa": "Español",
                    "eng": "Inglés",
                }.get(code, code.upper())
                available[name] = code
    if not available:
        available["Español"] = "spa"
        available["Inglés"] = "eng"
    return available


def ocr_document(
    doc: fitz.Document,
    language: str = "spa",
    dpi: int = 300,
    pages: Sequence[int] | None = None,
    progress_callback: Callable[[int, int], bool] | None = None,
) -> fitz.Document:
    """Aplica OCR sobre las páginas indicadas y devuelve un nuevo documento con texto buscable."""
    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    total = len(target_pages)
    out_doc = fitz.open()

    for idx, pno in enumerate(target_pages):
        if progress_callback and not progress_callback(idx + 1, total):
            out_doc.close()
            raise InterruptedError("Operación de OCR cancelada por el usuario.")

        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi)
        try:
            ocr_bytes = pix.pdfocr_tobytes(language=language, tessdata=TESSDATA_DIR)
            with fitz.open("pdf", ocr_bytes) as ocr_page_doc:
                out_doc.insert_pdf(ocr_page_doc)
        except Exception:
            # Fallback en caso de que la página no contenga texto reconocible
            with fitz.open("pdf", pix.pdfocr_tobytes(language="eng", tessdata=TESSDATA_DIR) if language != "eng" else pix.tobytes("pdf")) as ocr_page_doc:
                out_doc.insert_pdf(ocr_page_doc)

    return out_doc
