"""Optimización y compresión inteligente de documentos PDF para aseguradoras y empresas."""
from __future__ import annotations

import os
import pymupdf as fitz
from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QImage
from .document_io import serialize_pdf, clone_pdf, save_pdf

PROFILE_EMAIL = "email"
PROFILE_STANDARD = "standard"
PROFILE_HIGH = "high"
PROFILE_CUSTOM = "custom"

PROFILES = {
    PROFILE_EMAIL: {
        "name": "📧 Envío por Correo / Póliza Ligera (Objetivo < 5 MB)",
        "desc": "Compresión alta y reducción de fotos a 130 DPI (objetivo < 5 MB según contenido). Ideal para enviar pólizas por email.",
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


def _compute_max_physical_inches(doc: fitz.Document) -> dict[int, tuple[float, float]]:
    """Calcula para cada xref de imagen su mayor tamaño físico de aparición (en pulgadas) en todo el PDF (H25)."""
    max_inches: dict[int, tuple[float, float]] = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for r in rects:
                w_in = max(0.0, r.width / 72.0)
                h_in = max(0.0, r.height / 72.0)
                if w_in > 0 and h_in > 0:
                    prev_w, prev_h = max_inches.get(xref, (0.0, 0.0))
                    max_inches[xref] = (max(prev_w, w_in), max(prev_h, h_in))
    return max_inches


def optimize_document(
    doc: fitz.Document,
    out_path: str,
    compress_images: bool = True,
    image_quality: int = 80,
    max_dpi: int = 180,
    sanitize_metadata: bool = False,
    max_dim: int = 1800,
    remove_xfa: bool = False,
) -> tuple[int, int, float]:
    """Optimiza el PDF reduciendo su peso, recomprimiendo imágenes según DPI físico, aplicando subconjunto de fuentes
    y compactando tablas de objetos en streams (H01, N01, H09, H25).
    Retorna (bytes_iniciales, bytes_finales, porcentaje_ahorro).
    """
    initial_bytes = serialize_pdf(doc)
    initial_size = len(initial_bytes)

    # Clonar documento en memoria para trabajar sin alterar el original
    opt_doc = clone_pdf(doc)

    if sanitize_metadata:
        from .security import sanitize_document, sanitize_metadata as clean_metadata
        try:
            sanitize_document(opt_doc, remove_xfa=remove_xfa)
            clean_metadata(opt_doc)
        except Exception:
            opt_doc.close()
            raise
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
        max_phys = _compute_max_physical_inches(opt_doc)
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
                    w, h = int(base["width"]), int(base["height"])
                    raw_len = len(base["image"])
                    smask_xref = int(base.get("smask", 0) or 0) or int(img_info[1] or 0)

                    # Determinar límite efectivo en píxeles considerando el tamaño físico mayor y max_dpi (H25)
                    eff_max_w = max_dim if max_dim > 0 else w
                    eff_max_h = max_dim if max_dim > 0 else h
                    if max_dpi > 0 and xref in max_phys:
                        phys_w_in, phys_h_in = max_phys[xref]
                        if phys_w_in > 0 and phys_h_in > 0:
                            dpi_w = max(1, round(phys_w_in * max_dpi))
                            dpi_h = max(1, round(phys_h_in * max_dpi))
                            eff_max_w = min(eff_max_w, dpi_w)
                            eff_max_h = min(eff_max_h, dpi_h)

                    needs_downscale = (w > eff_max_w) or (h > eff_max_h)

                    # N01: Si la imagen tiene máscara de transparencia (SMask > 0), NUNCA convertir a JPEG opaco
                    if smask_xref > 0:
                        if needs_downscale:
                            base_pix = fitz.Pixmap(opt_doc, xref)
                            mask_pix = fitz.Pixmap(opt_doc, smask_xref)
                            if base_pix.colorspace != fitz.csRGB:
                                base_pix = fitz.Pixmap(fitz.csRGB, base_pix)
                            rgba_pix = fitz.Pixmap(base_pix, mask_pix)
                            qimg = QImage(
                                rgba_pix.samples,
                                rgba_pix.width,
                                rgba_pix.height,
                                rgba_pix.stride,
                                QImage.Format_RGBA8888_Premultiplied,
                            ).copy()
                            scaled = qimg.scaled(
                                eff_max_w, eff_max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QBuffer.WriteOnly)
                            scaled.save(buf, "PNG")
                            png_data = bytes(ba.data())
                            if len(png_data) < raw_len:
                                try:
                                    page.replace_image(xref, stream=png_data)
                                except Exception:
                                    pass
                        continue

                    # Imagen opaca sin SMask
                    if needs_downscale or raw_len > 10000 or base.get("ext") in ("png", "bmp", "tiff", "tif"):
                        pix = fitz.Pixmap(opt_doc, xref)
                        if pix.alpha:
                            # Si el propio pixmap posee canal alfa, preservarlo sin pasar a JPEG
                            continue

                        if pix.n >= 5:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        elif pix.colorspace != fitz.csRGB and pix.n not in (1, 3):
                            pix = fitz.Pixmap(fitz.csRGB, pix)

                        is_gray = (pix.n == 1 or pix.colorspace == fitz.csGRAY)
                        fmt = QImage.Format_Grayscale8 if is_gray else QImage.Format_RGB888

                        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                        if needs_downscale:
                            scaled = qimg.scaled(
                                eff_max_w, eff_max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                        else:
                            scaled = qimg

                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QBuffer.WriteOnly)
                        scaled.save(buf, "JPEG", image_quality)
                        compressed_data = bytes(ba.data())

                        # Reemplazar si bajó el tamaño o si se redujo resolución explícitamente por max_dpi
                        if len(compressed_data) < raw_len or needs_downscale:
                            try:
                                page.replace_image(xref, stream=compressed_data)
                            except Exception:
                                # H01/N01: NUNCA usar update_stream con JPEG sobre un diccionario incompatible
                                pass
                except Exception:
                    continue

    # Optimización y subconjunto de fuentes (descarta caracteres no utilizados)
    try:
        opt_doc.subset_fonts()
    except Exception:
        pass

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # Guardar con compactación máxima, compresión deflate profunda y streams de objetos
    save_pdf(
        opt_doc, out_path,
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
    # Salvaguarda: si la optimización incrementara el peso y NO se solicitó sanitización ni reducción de DPI efectiva,
    # mantener la copia original. Si se solicitó sanitización, preservamos el archivo limpio (H09).
    if final_size > initial_size and initial_size > 0 and not sanitize_metadata and not compress_images:
        with open(out_path, "wb") as f:
            f.write(initial_bytes)
        final_size = initial_size

    saving = max(0.0, (1.0 - (final_size / max(1, initial_size))) * 100.0)
    return initial_size, final_size, round(saving, 1)
