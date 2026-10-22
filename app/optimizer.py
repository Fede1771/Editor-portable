"""Optimización y compresión inteligente de documentos PDF para aseguradoras y empresas."""
from __future__ import annotations

import os
import pymupdf as fitz
from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QImage

PROFILE_EMAIL = "email"
PROFILE_STANDARD = "standard"
PROFILE_HIGH = "high"
PROFILE_CUSTOM = "custom"

PROFILES = {
    PROFILE_EMAIL: {
        "name": "📧 Envío por Correo / Póliza Ligera (< 5 MB)",
        "desc": "Compresión alta y reducción de fotos a 130 DPI. Ideal para enviar pólizas o denuncias por email.",
        "quality": 65,
        "max_dpi": 130,
        "sanitize": True,
        "max_dim": 1300,
    },
    PROFILE_STANDARD: {
        "name": "📂 Archivo Digital Corporativo (Equilibrado)",
        "desc": "Equilibrio óptimo entre nitidez visual en pantalla y peso reducido (180 DPI, calidad 80%).",
        "quality": 80,
        "max_dpi": 180,
        "sanitize": False,
        "max_dim": 1800,
    },
    PROFILE_HIGH: {
        "name": "⚖️ Legajo Pericial / Siniestros (Máxima Nitidez)",
        "desc": "Preserva al máximo la fidelidad de fotos de daños, firmas y sellos periciales (300 DPI, calidad 92%).",
        "quality": 92,
        "max_dpi": 300,
        "sanitize": False,
        "max_dim": 3000,
    },
}


def optimize_document(
    doc: fitz.Document,
    out_path: str,
    compress_images: bool = True,
    image_quality: int = 80,
    max_dpi: int = 180,
    sanitize_metadata: bool = False,
    max_dim: int = 1800,
) -> tuple[int, int, float]:
    """Optimiza el PDF reduciendo su peso, recomprimiendo imágenes y limpiando objetos huérfanos.

    Retorna (bytes_iniciales, bytes_finales, porcentaje_ahorro).
    """
    initial_bytes = doc.tobytes()
    initial_size = len(initial_bytes)

    # Clonar documento en memoria para trabajar sin alterar el original
    opt_doc = fitz.open("pdf", initial_bytes)

    if sanitize_metadata:
        # Limpieza de metadatos sensibles (autor, software de creación, fechas internas)
        opt_doc.set_metadata({})

    if compress_images:
        for pno in range(opt_doc.page_count):
            page = opt_doc[pno]
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base = opt_doc.extract_image(xref)
                    w, h = base["width"], base["height"]

                    # Solo procesar si supera los límites razonables
                    if w > max_dim or h > max_dim or (w > 500 and base.get("ext") in ("png", "bmp")):
                        pix = fitz.Pixmap(opt_doc, xref)
                        if pix.n >= 5:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        elif pix.colorspace != fitz.csRGB and pix.n != 3:
                            pix = fitz.Pixmap(fitz.csRGB, pix)

                        # Reescalado de alta fidelidad con QImage
                        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                        if w > max_dim or h > max_dim:
                            scaled = qimg.scaled(max_dim, max_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        else:
                            scaled = qimg

                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QBuffer.WriteOnly)
                        scaled.save(buf, "JPEG", image_quality)
                        compressed_data = bytes(ba.data())

                        # Solo reemplazar si los bytes resultantes son efectivamente menores
                        if len(compressed_data) < len(base["image"]):
                            opt_doc.update_stream(xref, compressed_data)
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
