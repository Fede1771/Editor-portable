"""Optimización de documentos PDF (fase 10): reducción de tamaño, compresión de imágenes y limpieza."""
from __future__ import annotations

import os

import pymupdf as fitz


def optimize_document(
    doc: fitz.Document,
    out_path: str,
    compress_images: bool = True,
    image_quality: int = 75,
    max_dpi: int = 150,
    sanitize_metadata: bool = False,
) -> tuple[int, int, float]:
    """Optimiza el PDF reduciendo su peso y limpiando recursos huérfanos.

    Retorna (bytes_iniciales, bytes_finales, porcentaje_ahorro).
    """
    initial_bytes = doc.tobytes()
    initial_size = len(initial_bytes)

    # Clonar documento en memoria para trabajar sobre él
    opt_doc = fitz.open("pdf", initial_bytes)

    if sanitize_metadata:
        # Limpieza de metadatos sensibles
        opt_doc.set_metadata({})

    if compress_images:
        # Recomprimir imágenes incrustadas que superen la resolución objetivo
        for pno in range(opt_doc.page_count):
            page = opt_doc[pno]
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base = opt_doc.extract_image(xref)
                    # Si es JPEG o PNG grande, recomprimir a calidad indicada
                    if base["width"] > 600 or base["height"] > 600:
                        pix = fitz.Pixmap(opt_doc, xref)
                        if pix.n >= 5:  # Si tiene canal alpha o CMYK, convertir a RGB
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        jpeg_bytes = pix.tobytes("jpeg", jpg_quality=image_quality)
                        # Reemplazar stream de imagen en xref
                        opt_doc.update_stream(xref, jpeg_bytes)
                except Exception:
                    continue

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # Guardar con compactación máxima de objetos, compresión deflate y limpieza de huérfanos
    opt_doc.save(
        out_path,
        garbage=4,
        deflate=True,
        clean=True,
        linear=False,
    )
    opt_doc.close()

    final_size = os.path.getsize(out_path)
    saving = max(0.0, (1.0 - (final_size / max(1, initial_size))) * 100.0)
    return initial_size, final_size, round(saving, 1)
