"""Copias y guardado PDF que conservan cifrado, permisos y autenticación."""
from __future__ import annotations

import os
import tempfile
import pymupdf as fitz


def serialize_pdf(doc: fitz.Document) -> bytes:
    # needs_pass=False también ocurre con cifrado owner-only. No degradar a texto claro.
    return doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)


def open_pdf(data: bytes, password: str | None = None) -> fitz.Document:
    doc = fitz.open("pdf", data)
    if doc.needs_pass and (password is None or not doc.authenticate(password)):
        doc.close()
        raise ValueError("No se pudo autenticar la copia protegida del documento.")
    if password is not None:
        doc._editorpdf_password = password
    return doc


def clone_pdf(doc: fitz.Document) -> fitz.Document:
    return open_pdf(serialize_pdf(doc), getattr(doc, "_editorpdf_password", None))


def save_pdf(doc: fitz.Document, path: str, **options) -> None:
    """Temporal propio, verificación y reemplazo sólo al completarse."""
    target = os.path.abspath(path)
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=folder)
    os.close(fd)
    try:
        doc.save(temp, encryption=fitz.PDF_ENCRYPT_KEEP, **options)
        with open(temp, "rb") as stream:
            data = stream.read()
        with open_pdf(data, getattr(doc, "_editorpdf_password", None)) as check:
            if check.page_count != doc.page_count:
                raise ValueError("El PDF guardado no conserva el número de páginas.")
            if check.metadata.get("encryption") != doc.metadata.get("encryption"):
                raise ValueError("El PDF guardado no conserva el cifrado original.")
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            from .privacy import secure_wipe_file
            secure_wipe_file(temp)


def selected_copy(doc: fitz.Document, pages: list[int]) -> fitz.Document:
    if not pages or any(p < 0 or p >= doc.page_count for p in pages):
        raise ValueError("La selección de páginas no es válida.")
    result = clone_pdf(doc)
    try:
        result.select(pages)
        for name in list(result.embfile_names()):
            result.embfile_del(name)
        return result
    except Exception:
        result.close()
        raise
