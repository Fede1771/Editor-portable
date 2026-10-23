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


def _restore_links_and_toc(
    out_doc: fitz.Document,
    toc_before: list,
    links_by_page: dict[int, list[dict]],
    replaced_pages: set[int],
) -> None:
    """Reconstruye enlaces internos/externos en páginas reemplazadas y marcadores del documento (V03)."""
    for pno in sorted(replaced_pages):
        if pno < 0 or pno >= out_doc.page_count:
            continue
        page = out_doc[pno]
        for lnk in links_by_page.get(pno, []):
            kind = lnk.get("kind")
            if kind not in (fitz.LINK_GOTO, fitz.LINK_URI, fitz.LINK_NAMED):
                continue
            clean_lnk = {k: v for k, v in lnk.items() if k not in ("xref", "id")}
            if kind == fitz.LINK_GOTO:
                target_pg = clean_lnk.get("page", -1)
                if not isinstance(target_pg, int) or target_pg < 0 or target_pg >= out_doc.page_count:
                    continue
            try:
                page.insert_link(clean_lnk)
            except Exception:
                pass

    if toc_before:
        restored_toc = []
        for item in toc_before:
            if len(item) < 3:
                continue
            lvl, title, pg = item[0], item[1], item[2]
            if isinstance(pg, int) and 1 <= pg <= out_doc.page_count:
                dest = dict(item[3]) if len(item) > 3 and isinstance(item[3], dict) else {}
                dest.pop("xref", None)
                if dest and dest.get("kind") == fitz.LINK_GOTO:
                    dest["page"] = pg - 1
                    restored_toc.append([lvl, title, pg, dest])
                else:
                    restored_toc.append([lvl, title, pg])
            else:
                restored_toc.append([lvl, title, -1])
        try:
            out_doc.set_toc(restored_toc)
        except Exception:
            try:
                out_doc.set_toc([[it[0], it[1], it[2]] for it in restored_toc])
            except Exception:
                pass


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
        toc_before = out_doc.get_toc(simple=False)
        links_by_page = {
            pno: [dict(lnk) for lnk in out_doc[pno].get_links()]
            for pno in target_pages
        }
        replaced_pages: set[int] = set()

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
                        out_doc.insert_pdf(recognized, start_at=pno)
                        out_doc.delete_page(pno + 1)
                    replaced_pages.add(pno)
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

        if replaced_pages:
            _restore_links_and_toc(out_doc, toc_before, links_by_page, replaced_pages)

        report["status"] = "failed" if not report["recognized"] else ("partial" if report["failed"] else "success")
        out_doc._editorpdf_ocr_report = report
    except Exception:
        out_doc.close()
        raise
    return out_doc
