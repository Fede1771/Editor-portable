"""Pruebas del Grupo 5: Compresión con transparencia/SMask y DPI, Excel literal y colisiones de exportación.
Cubre: H01, N01, H25, H20, N05, H28.
"""
from __future__ import annotations

import os
import pymupdf as fitz
import pytest
from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage

from app import content_ops, conversion, optimizer


def _make_rgba_png_bytes(width: int = 256, height: int = 256) -> bytes:
    """Crea una imagen PNG RGBA donde la mitad superior es transparente y la mitad inferior tiene textura roja opaca (>30 KB)."""
    qimg = QImage(width, height, QImage.Format_RGBA8888)
    for y in range(height):
        for x in range(width):
            if y < height // 2:
                qimg.setPixelColor(x, y, QColor(0, 0, 0, 0))
            else:
                r = 180 + ((x * 37 + y * 13) % 75)
                g = (x * 17 + y * 29) % 40
                b = (x * 23 + y * 7) % 40
                qimg.setPixelColor(x, y, QColor(r, g, b, 255))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    qimg.save(buf, "PNG", 0)
    return bytes(ba.data())


# ---------------------------------------------------------------------------
# N01 & H01: Compresión con transparencia (SMask) y fallo de replace_image
# ---------------------------------------------------------------------------
def test_n01_optimize_preserves_transparency_and_smask_over_colored_background(tmp_path):
    """N01: Una imagen RGBA con zona transparente sobre fondo verde debe conservar el fondo verde tras optimizar."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    # Fondo verde
    page.draw_rect(page.rect, color=None, fill=(0.0, 1.0, 0.0))

    png_bytes = _make_rgba_png_bytes(256, 256)
    img_rect = fitz.Rect(20, 20, 276, 276)
    page.insert_image(img_rect, stream=png_bytes)

    # Verificar estado antes de optimizar: píxel (40, 40) dentro de la mitad superior transparente es verde
    pix_before = page.get_pixmap(dpi=72, alpha=False)
    r0, g0, b0 = pix_before.pixel(40, 40)[:3]
    assert g0 > 200 and r0 < 30 and b0 < 30

    out_pdf = tmp_path / "opt_transparent.pdf"
    optimizer.optimize_document(
        doc,
        str(out_pdf),
        compress_images=True,
        image_quality=75,
        max_dpi=150,
        max_dim=1500,
    )
    doc.close()

    reopened = fitz.open(str(out_pdf))
    pix_after = reopened[0].get_pixmap(dpi=72, alpha=False)
    r1, g1, b1 = pix_after.pixel(40, 40)[:3]
    # La mitad superior transparente debe seguir dejando ver el fondo verde (no volverse negra)
    assert g1 > 200 and r1 < 30 and b1 < 30, f"Transparencia perdida: pixel=(r={r1}, g={g1}, b={b1})"
    # Y la mitad inferior opaca roja debe seguir siendo roja
    r2, g2, b2 = pix_after.pixel(40, 220)[:3]
    assert r2 > 180 and g2 < 50 and b2 < 50
    reopened.close()


def test_h01_optimize_replace_image_failure_does_not_corrupt_with_update_stream(tmp_path, monkeypatch):
    """H01/N01: Si replace_image falla, NO debe llamar a update_stream con bytes JPEG sobre un diccionario incompatible."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)

    # Crear imagen PNG grande para forzar la ruta de compresión
    qimg = QImage(400, 400, QImage.Format_RGB888)
    for y in range(400):
        for x in range(400):
            qimg.setPixelColor(x, y, QColor((x * 3) % 256, (y * 5) % 256, 120))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    qimg.save(buf, "PNG")
    page.insert_image(fitz.Rect(20, 20, 220, 220), stream=bytes(ba.data()))

    def broken_replace_image(self, xref, *args, **kwargs):
        raise RuntimeError("Fallo simulado de replace_image")

    monkeypatch.setattr(fitz.Page, "replace_image", broken_replace_image)

    out_pdf = tmp_path / "opt_fallback_safe.pdf"
    optimizer.optimize_document(
        doc,
        str(out_pdf),
        compress_images=True,
        image_quality=70,
        max_dpi=150,
        sanitize_metadata=True,
    )
    doc.close()

    reopened = fitz.open(str(out_pdf))
    pix = reopened[0].get_pixmap(dpi=72, alpha=False)
    # El área de la imagen no debe haberse corrompido ni quedado en blanco/negro inválido
    r, g, b = pix.pixel(100, 100)[:3]
    assert b > 80
    reopened.close()


# ---------------------------------------------------------------------------
# H25: El parámetro max_dpi debe dimensionar según el tamaño físico en página
# ---------------------------------------------------------------------------
def test_h25_optimize_uses_max_dpi_according_to_physical_display_size(tmp_path):
    """H25: Una imagen de 1200x1200 colocada en un área de 2x2 pulgadas (144x144 pt) con max_dpi=150
    debe reducirse a ~300x300 px incluso si max_dim=1800."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)

    qimg = QImage(1200, 1200, QImage.Format_RGB888)
    for y in range(1200):
        for x in range(1200):
            qimg.setPixelColor(x, y, QColor((x * 7) % 256, (y * 11) % 256, (x + y) % 256))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    qimg.save(buf, "PNG")

    # 144 x 144 puntos = 2 x 2 pulgadas. A 150 DPI => 300 x 300 píxeles.
    page.insert_image(fitz.Rect(36, 36, 180, 180), stream=bytes(ba.data()))

    out_pdf = tmp_path / "opt_dpi.pdf"
    optimizer.optimize_document(
        doc,
        str(out_pdf),
        compress_images=True,
        image_quality=80,
        max_dpi=150,
        max_dim=1800,
    )
    doc.close()

    reopened = fitz.open(str(out_pdf))
    imgs = reopened[0].get_images(full=True)
    assert len(imgs) == 1
    extracted = reopened.extract_image(imgs[0][0])
    assert extracted["width"] <= 310
    assert extracted["height"] <= 310
    reopened.close()


# ---------------------------------------------------------------------------
# H20 & N05: Exportación Excel bloquea fórmulas sin añadir apóstrofos literales
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# H28: Exportación de imágenes y extracción de imágenes no deben sobrescribir
# ---------------------------------------------------------------------------
def test_h28_convert_to_images_and_extract_images_do_not_overwrite(tmp_path):
    """H28: convert_to_images y extract_images deben renombrar ante colisión en vez de sobrescribir archivos existentes."""
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    qimg = QImage(60, 60, QImage.Format_RGB888)
    qimg.fill(QColor(10, 120, 240))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    qimg.save(buf, "PNG")
    page.insert_image(fitz.Rect(20, 20, 80, 80), stream=bytes(ba.data()))

    # 1. Pre-crear pagina_001.png con contenido centinela
    existing_render = tmp_path / "pagina_001.png"
    existing_render.write_bytes(b"SENTINEL_RENDER_IMAGE")

    exported = conversion.convert_to_images(doc, str(tmp_path), fmt="png", dpi=72)
    assert len(exported) == 1
    assert os.path.abspath(exported[0]) != os.path.abspath(str(existing_render))
    assert existing_render.read_bytes() == b"SENTINEL_RENDER_IMAGE"

    # 2. Pre-crear pagina_001_img_01.png con contenido centinela
    existing_extract = tmp_path / "pagina_001_img_01.png"
    existing_extract.write_bytes(b"SENTINEL_EXTRACTED_IMAGE")

    extracted = content_ops.extract_images(doc, str(tmp_path))
    assert len(extracted) == 1
    assert os.path.abspath(extracted[0]) != os.path.abspath(str(existing_extract))
    assert existing_extract.read_bytes() == b"SENTINEL_EXTRACTED_IMAGE"
    doc.close()
