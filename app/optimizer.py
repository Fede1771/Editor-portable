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
    """Optimiza el PDF reduciendo su peso, recomprimiendo imágenes, aplicando subconjunto de fuentes

    y compactando tablas de objetos en streams.
    Retorna (bytes_iniciales, bytes_finales, porcentaje_ahorro).
    """
    initial_bytes = doc.tobytes()
    initial_size = len(initial_bytes)

    # Clonar documento en memoria para trabajar sin alterar el original
    opt_doc = fitz.open("pdf", initial_bytes)

    if sanitize_metadata:
        opt_doc.set_metadata({})
        try:
            opt_doc.scrub(
                attached_files=False,
                clean_pages=True,
                embedded_files=False,
                hidden_text=False,
                javascript=True,
                metadata=True,
                redactions=False,
                remove_links=False,
                reset_fields=False,
                reset_responses=False,
                thumbnails=True,
                xml_metadata=True,
            )
        except Exception:
            pass

    if compress_images:
        processed_xrefs: set[int] = set()
        for pno in range(opt_doc.page_count):
            page = opt_doc[pno]
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in processed_xrefs:
                    continue
                processed_xrefs.add(xref)
                try:
                    base = opt_doc.extract_image(xref)
                    w, h = base["width"], base["height"]
                    raw_len = len(base["image"])

                    # Recomprimir si excede dimensiones o si es una imagen con peso relevante
                    if w > max_dim or h > max_dim or raw_len > 10000 or base.get("ext") in ("png", "bmp", "tiff", "tif"):
                        pix = fitz.Pixmap(opt_doc, xref)

                        # Detección y normalización de espacio de color
                        if pix.n >= 5:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        elif pix.colorspace != fitz.csRGB and pix.n not in (1, 3):
                            pix = fitz.Pixmap(fitz.csRGB, pix)

                        is_gray = (pix.n == 1 or pix.colorspace == fitz.csGRAY)
                        fmt = QImage.Format_Grayscale8 if is_gray else QImage.Format_RGB888

                        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                        if w > max_dim or h > max_dim:
                            scaled = qimg.scaled(max_dim, max_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        else:
                            scaled = qimg

                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QBuffer.WriteOnly)
                        scaled.save(buf, "JPEG", image_quality)
                        compressed_data = bytes(ba.data())

                        # Solo reemplazar si los bytes resultantes son estrictamente menores
                        if len(compressed_data) < raw_len:
                            try:
                                page.replace_image(xref, stream=compressed_data)
                            except Exception:
                                opt_doc.update_stream(xref, compressed_data)
                except Exception:
                    continue

    # Optimización y subconjunto de fuentes (descarta caracteres no utilizados)
    try:
        opt_doc.subset_fonts()
    except Exception:
        pass

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # Guardar con compactación máxima, compresión deflate profunda y streams de objetos
    opt_doc.save(
        out_path,
        garbage=4,
        clean=True,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        use_objstms=1,
        linear=False,
    )
    opt_doc.close()

    final_size = os.path.getsize(out_path)
    # Salvaguarda: si por alguna razón la optimización incrementara el peso y NO se solicitó sanitización,
    # mantener la copia original. Si se solicitó sanitización, preservamos el archivo limpio.
    if final_size > initial_size and initial_size > 0 and not sanitize_metadata:
        with open(out_path, "wb") as f:
            f.write(initial_bytes)
        final_size = initial_size

    saving = max(0.0, (1.0 - (final_size / max(1, initial_size))) * 100.0)
    return initial_size, final_size, round(saving, 1)
