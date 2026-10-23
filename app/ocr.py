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
    """Aplica OCR sobre las páginas indicadas y devuelve un nuevo documento con texto buscable (H31)."""
    from .document_io import selected_copy
    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    total = len(target_pages)
    out_doc = selected_copy(doc, target_pages)
    report = {"recognized": [], "failed": [], "fallback_language": []}
    try:
        for idx, pno in enumerate(target_pages):
            if progress_callback and not progress_callback(idx + 1, total):
                raise InterruptedError("Operación de OCR cancelada por el usuario.")
            pix = doc[pno].get_pixmap(dpi=dpi, alpha=False)
            languages = [language]
            if language != "eng" and os.path.isfile(os.path.join(TESSDATA_DIR, "eng.traineddata")):
                languages.append("eng")
            inserted = False
            error = ""
            for candidate in languages:
                try:
                    data = pix.pdfocr_tobytes(language=candidate, tessdata=TESSDATA_DIR)
                    with fitz.open("pdf", data) as recognized:
                        if not any(p.get_text().strip() for p in recognized):
                            raise ValueError("El motor no reconoció texto en esta página.")
                        out_doc.insert_pdf(recognized, start_at=idx)
                        out_doc.delete_page(idx + 1)
                    report["recognized"].append(pno + 1)
                    if candidate != language:
                        report["fallback_language"].append(pno + 1)
                    inserted = True
                    break
                except Exception as exc:
                    error = str(exc)
            if not inserted:
                # Conservar página original, texto, geometría y datos; no rasterizar como falso éxito.
                report["failed"].append({"page": pno + 1, "error": error})
        report["status"] = "failed" if not report["recognized"] else ("partial" if report["failed"] else "success")
        out_doc._editorpdf_ocr_report = report
    except Exception:
        out_doc.close()
        raise
    return out_doc
