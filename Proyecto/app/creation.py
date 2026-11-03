"""Combinación de archivos PDF e imágenes en un único documento."""
from __future__ import annotations

import html as html_lib
import io
import os
import pathlib
import sys

import pymupdf as fitz


def _resolve_data_dir() -> str:
    """Resuelve la ruta del directorio data/ de forma robusta."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, "_MEIPASS", exe_dir)
        candidates.extend([
            os.path.join(meipass, "data"),
            os.path.join(exe_dir, "_internal", "data"),
            os.path.join(exe_dir, "data"),
        ])
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(app_root, "data"))
    for cand in candidates:
        if os.path.isdir(cand):
            return cand
    return candidates[0]


DATA_DIR = _resolve_data_dir()

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".bmp", ".gif", ".tif", ".tiff", ".jp2"}

IMAGE_MODES = {
    "Tamaño de la imagen": "image",
    "A4 (ajustada)": "a4",
    "Carta (ajustada)": "letter",
}

MAX_IMAGE_PAGE = 1191.0          # lado máximo (pt) de una página creada a partir de una imagen


def file_filter() -> str:
    exts = sorted(IMAGE_EXTS | {".pdf"})
    return "Archivos compatibles (" + " ".join(f"*{e}" for e in exts) + ");;Archivos PDF (*.pdf);;Imágenes (*.png *.jpg *.jpeg *.bmp *.tiff);;Todos los archivos (*)"


def classify(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    return None


# --------------------------------------------------------------------- imágenes
def _append_image(doc: fitz.Document, path: str, mode: str) -> None:
    with fitz.open(path) as img:
        src = fitz.open("pdf", img.convert_to_pdf())
    try:
        for i in range(src.page_count):
            sr = src[i].rect
            if mode == "image":
                k = min(1.0, MAX_IMAGE_PAGE / max(sr.width, sr.height))
                page = doc.new_page(width=sr.width * k, height=sr.height * k)
                page.show_pdf_page(page.rect, src, i)
            else:
                w, h = (595.0, 842.0) if mode == "a4" else (612.0, 792.0)
                if sr.width > sr.height:
                    w, h = h, w
                page = doc.new_page(width=w, height=h)
                page.show_pdf_page(page.rect + (18, 18, -18, -18), src, i)
    finally:
        src.close()


def images_to_pdf(paths: list[str], mode: str = "image") -> fitz.Document:
    if not paths:
        raise ValueError("No hay imágenes para convertir.")
    doc = fitz.open()
    try:
        for p in paths:
            try:
                _append_image(doc, p, mode)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"No se pudo leer la imagen «{os.path.basename(p)}»: {exc}") from exc
    except Exception:
        doc.close()
        raise
    return doc


# ------------------------------------------------------------------ HTML / texto (auxiliares)
def _read_text(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


MAX_HTML_PAGES = 500


def html_to_pdf(html: str, base_dir: str | None = None, css: str = "",
                pagesize: fitz.Rect | None = None, margin: float = 50.0) -> fitz.Document:
    """Convierte HTML a PDF con detección de falta de progreso y límite de páginas (H48)."""
    pagesize = pagesize or fitz.paper_rect("a4")
    where = pagesize + (margin, margin, -margin, -margin)
    archive = fitz.Archive(base_dir) if base_dir else None
    story = fitz.Story(html=html, user_css=css, archive=archive)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = 1
    page_count = 0
    prev_filled: fitz.Rect | None = None
    no_progress_streak = 0
    try:
        while more:
            page_count += 1
            if page_count > MAX_HTML_PAGES:
                raise ValueError(
                    f"El documento HTML supera el límite de {MAX_HTML_PAGES} páginas o contiene elementos no acomodables."
                )
            dev = writer.begin_page(pagesize)
            more, filled = story.place(where)
            story.draw(dev)
            writer.end_page()

            if more:
                filled_rect = fitz.Rect(filled)
                if prev_filled is not None and filled_rect == prev_filled and filled_rect.height < where.height * 0.25:
                    no_progress_streak += 1
                    if no_progress_streak >= 2:
                        raise ValueError(
                            "El contenido HTML contiene elementos que exceden el área imprimible de la página y no pueden paginarse."
                        )
                else:
                    no_progress_streak = 0
                prev_filled = filled_rect
    except Exception:
        try:
            writer.close()
        except Exception:
            pass
        raise
    writer.close()
    return fitz.open("pdf", buf.getvalue())


def text_to_pdf(path: str) -> fitz.Document:
    body = html_lib.escape(_read_text(path))
    css = "pre { font-family: monospace; font-size: 9pt; white-space: pre-wrap; }"
    return html_to_pdf(f"<pre>{body}</pre>", css=css)


def htmlfile_to_pdf(path: str) -> fitz.Document:
    return html_to_pdf(_read_text(path), base_dir=os.path.dirname(os.path.abspath(path)))


# --------------------------------------------------------------------- combinar
def build_pdf(paths: list[str], image_mode: str = "image", bookmarks: bool = True) -> fitz.Document:
    """Une archivos PDF e imágenes en un único PDF (en el orden dado)."""
    if not paths:
        raise ValueError("No hay archivos para combinar.")
    out = fitz.open()
    toc: list[list] = []
    try:
        for p in paths:
            kind = classify(p)
            start = out.page_count
            name = os.path.splitext(os.path.basename(p))[0]
            if kind == "pdf":
                part = fitz.open(p)
                if part.needs_pass:
                    part.close()
                    raise ValueError(f"«{os.path.basename(p)}» está protegido con contraseña.")
            elif kind == "image":
                part = images_to_pdf([p], image_mode)
            else:
                raise ValueError(f"Tipo de archivo no compatible: {os.path.basename(p)}")
            try:
                out.insert_pdf(part)
            finally:
                part.close()
            if out.page_count > start:
                toc.append([1, name, start + 1])
        if bookmarks and len(paths) > 1 and toc:
            out.set_toc(toc)
    except Exception:
        out.close()
        raise
    return out


def blank_document(pages: int = 1, size: str = "a4") -> fitz.Document:
    doc = fitz.open()
    rect = fitz.paper_rect(size)
    for _ in range(max(1, pages)):
        doc.new_page(width=rect.width, height=rect.height)
    return doc
