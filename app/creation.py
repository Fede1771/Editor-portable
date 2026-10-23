"""Crear PDF (fase 3): imágenes, Office (LibreOffice), HTML/texto, combinar y escáner."""
from __future__ import annotations

import html as html_lib
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
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
OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
HTML_EXTS = {".html", ".htm"}
TEXT_EXTS = {".txt", ".log", ".csv", ".md"}

IMAGE_MODES = {
    "Tamaño de la imagen": "image",
    "A4 (ajustada)": "a4",
    "Carta (ajustada)": "letter",
}

MAX_IMAGE_PAGE = 1191.0          # lado máximo (pt) de una página creada a partir de una imagen


def file_filter() -> str:
    exts = sorted(IMAGE_EXTS | OFFICE_EXTS | HTML_EXTS | TEXT_EXTS | {".pdf"})
    return "Archivos compatibles (" + " ".join(f"*{e}" for e in exts) + ");;Todos los archivos (*)"


def classify(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in OFFICE_EXTS:
        return "office"
    if ext in HTML_EXTS:
        return "html"
    if ext in TEXT_EXTS:
        return "text"
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


# ------------------------------------------------------------------ HTML / texto
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
                # Si place() no logra acomodar el elemento (filled muy pequeño o idéntico repetidamente sin llenar la página)
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


# ----------------------------------------------------------------------- Office
def find_soffice() -> str | None:
    found = shutil.which("soffice")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), r"C:\Program Files"):
        if base:
            cand = os.path.join(base, "LibreOffice", "program", "soffice.exe")
            if os.path.isfile(cand):
                return cand
    return None


def office_to_pdf_file(path: str, out_dir: str, timeout: int = 240) -> str:
    """Convierte con LibreOffice usando un perfil temporal aislado por conversión (H27)."""
    from .privacy import TempManager

    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("No se encontró LibreOffice. Instalalo para convertir documentos de Office.")
    profile = TempManager.create_temp_dir(prefix="editorpdf_lo_profile_")
    try:
        profile_url = pathlib.Path(profile).as_uri()      # codifica espacios y acentos de la ruta
        cmd = [soffice, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation={profile_url}",
               "--convert-to", "pdf", "--outdir", out_dir, path]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"LibreOffice tardó demasiado en convertir «{os.path.basename(path)}».") from exc
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
        if not os.path.isfile(out):
            raise RuntimeError(f"LibreOffice no pudo convertir «{os.path.basename(path)}».")
        return out
    finally:
        TempManager.cleanup_path(profile)


def convert_office_files(paths: list[str], out_dir: str) -> dict[str, str]:
    """Convierte (en bloque) los archivos de Office de la lista. Apto para un hilo en segundo plano."""
    from .privacy import TempManager

    result: dict[str, str] = {}
    for p in paths:
        if classify(p) == "office":
            sub = tempfile.mkdtemp(dir=out_dir)
            TempManager.register(sub)
            result[p] = office_to_pdf_file(p, sub)
    return result


# --------------------------------------------------------------------- combinar
def build_pdf(paths: list[str], image_mode: str = "image", bookmarks: bool = True,
              converted: dict[str, str] | None = None) -> fitz.Document:
    """Une archivos de distintos tipos en un único PDF (en el orden dado)."""
    if not paths:
        raise ValueError("No hay archivos para combinar.")
    converted = converted or {}
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
            elif kind == "office":
                if p not in converted:
                    raise ValueError(f"«{os.path.basename(p)}» no fue convertido.")
                part = fitz.open(converted[p])
            elif kind == "html":
                part = htmlfile_to_pdf(p)
            elif kind == "text":
                part = text_to_pdf(p)
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


# ----------------------------------------------------------------------- escáner
_SCAN_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$dlg = New-Object -ComObject WIA.CommonDialog
$img = $dlg.ShowAcquireImage(1, 1, 0x20000, '{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}', $false, $true, $false)
if ($img -ne $null) {
    $img.SaveFile($args[0])
    Write-Output $args[0]
}
"""


def scan_one_page(out_dir: str, index: int) -> str | None:
    """Abre el diálogo de escaneo de Windows (WIA). Devuelve la imagen o None si se cancela."""
    script = os.path.join(out_dir, "scan.ps1")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(_SCAN_SCRIPT)
    target = os.path.join(out_dir, f"scan_{index:03d}.png")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", script, target],
        capture_output=True, text=True, creationflags=flags, timeout=900)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        raise RuntimeError("No se pudo usar el escáner: " + (msg[0] if msg else "error desconocido"))
    return target if os.path.isfile(target) else None
