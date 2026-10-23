"""Exportación de páginas del PDF a imágenes de alta resolución (PNG, JPEG)."""
from __future__ import annotations

import os
import tempfile
from typing import Callable, Sequence

import pymupdf as fitz

from .attachments import unique_path


def _atomic_write_target(
    out_path: str,
    suffix: str,
    writer_fn: Callable[[str], None],
    verifier_fn: Callable[[str], None] | None = None,
) -> None:
    """Escribe en un archivo temporal en el mismo directorio, verifica y reemplaza atómicamente (V07)."""
    target = os.path.abspath(out_path)
    folder = os.path.dirname(target) or "."
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(target)}.",
        suffix=suffix,
        dir=folder,
    )
    os.close(fd)
    try:
        writer_fn(temp_path)
        if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
            raise OSError("El archivo generado está vacío o incompleto.")
        if verifier_fn is not None:
            verifier_fn(temp_path)
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            from .privacy import secure_wipe_file
            secure_wipe_file(temp_path)


def convert_to_images(
    doc: fitz.Document,
    out_dir: str,
    fmt: str = "png",
    dpi: int = 200,
    pages: Sequence[int] | None = None,
) -> list[str]:
    """Exporta las páginas del PDF como imágenes de alta resolución sin sobrescribir archivos existentes (H28, V08)."""
    from .viewer import render_bounded_pixmap

    os.makedirs(out_dir, exist_ok=True)
    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    exported: list[str] = []

    ext = fmt.lower().replace(".", "")
    for pno in target_pages:
        page = doc[pno]
        pix = render_bounded_pixmap(page, dpi=dpi, alpha=False)
        filename = f"pagina_{pno + 1:03d}.{ext}"
        out_path = unique_path(os.path.join(out_dir, filename))
        pix.save(out_path)
        exported.append(out_path)

    return exported
