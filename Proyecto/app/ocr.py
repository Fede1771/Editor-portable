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


def pages_with_unpreserved_elements(
    doc: fitz.Document,
    pages: Sequence[int] | None = None,
) -> dict[str, list[int]]:
    """Detecta páginas con widgets de formulario o anotaciones no-enlace que el reemplazo OCR descartaría (V03)."""
    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    form_pages: list[int] = []
    annot_pages: list[int] = []
    for pno in target_pages:
        if pno < 0 or pno >= doc.page_count:
            continue
        page = doc[pno]
        try:
            if list(page.widgets() or []):
                form_pages.append(pno + 1)
        except Exception:
            pass
        try:
            non_link = [
                a for a in (page.annots() or [])
                if getattr(a, "type", (None,))[0] != fitz.PDF_ANNOT_LINK
            ]
            if non_link:
                annot_pages.append(pno + 1)
        except Exception:
            pass
    return {"forms": form_pages, "annotations": annot_pages}


class _OCRPreservationError(RuntimeError):
    pass


def _replace_recognized_content(doc: fitz.Document, pno: int, recognized: fitz.Document) -> None:
    """Conservar el objeto Page, cajas, rotación, UserUnit y referencias entrantes.

    El raster OCR ya está orientado como la página visible: se desrota al colocarlo
    sobre el espacio de contenido original. Sólo se desconectan los contenidos
    previos después de preparar correctamente el nuevo XObject.
    """
    try:
        page = doc[pno]
        old_contents = set(page.get_contents())
        rotation = page.rotation
        # MuPDF expone una matriz de transformación distinta con Rotate activo,
        # particularmente con CropBox/UserUnit. Colocar en el espacio sin giro.
        page.set_rotation(0)
        try:
            page.show_pdf_page(page.rect, recognized, 0, rotate=rotation)
        finally:
            page.set_rotation(rotation)
        new_contents = [x for x in page.get_contents() if x not in old_contents]
        if not new_contents:
            raise ValueError("No se generó contenido OCR para la página.")
        doc.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in new_contents) + "]")
        # Las apariencias ya se rasterizaron. La interfaz exige consentimiento
        # antes de convertir widgets y comentarios a contenido fijo.
        for widget in list(page.widgets()):
            page.delete_widget(widget)
        for annot in list(page.annots()):
            page.delete_annot(annot)
    except Exception as exc:
        # No presentar como fallo de reconocimiento ni devolver una copia parcial.
        raise _OCRPreservationError(f"No se pudo conservar la estructura de la página {pno + 1}: {exc}") from exc


def ocr_document(
    doc: fitz.Document,
    language: str = "spa",
    dpi: int = 300,
    pages: Sequence[int] | None = None,
    progress_callback: Callable[[int, int], bool] | None = None,
) -> fitz.Document:
    """Aplica OCR sobre las páginas indicadas y devuelve un nuevo documento con texto buscable (H31, V03)."""
    from .document_io import clone_pdf
    from .viewer import render_bounded_pixmap

    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    if not target_pages or any(p < 0 or p >= doc.page_count for p in target_pages):
        raise ValueError("La selección de páginas no es válida.")
    total = len(target_pages)
    # V03: usar clone_pdf en lugar de selected_copy para conservar adjuntos (embfile_*),
    # marcadores (/Outlines) y enlaces internos del documento.
    out_doc = clone_pdf(doc)
    unpreserved = pages_with_unpreserved_elements(doc, target_pages)
    report = {
        "recognized": [],
        "failed": [],
        "fallback_language": [],
        "unpreserved_elements": unpreserved,
    }
    try:
        for idx, pno in enumerate(target_pages):
            if progress_callback and not progress_callback(idx + 1, total):
                raise InterruptedError("Operación de OCR cancelada por el usuario.")
            pix = render_bounded_pixmap(doc[pno], dpi=dpi, alpha=False)
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
                        _replace_recognized_content(out_doc, pno, recognized)
                    report["recognized"].append(pno + 1)
                    if candidate != language:
                        report["fallback_language"].append(pno + 1)
                    inserted = True
                    break
                except _OCRPreservationError:
                    raise
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
