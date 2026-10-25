"""Impresión del documento en memoria mediante los controladores instalados en Windows."""
from __future__ import annotations

import pymupdf as fitz
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter

from .viewer import render_bounded_pixmap


def print_page_indices(doc: fitz.Document, printer: QPrinter, current_page: int,
                       selected_pages: list[int]) -> list[int]:
    mode = printer.printRange()
    if mode == QPrinter.PrintRange.CurrentPage:
        pages = [current_page]
    elif mode == QPrinter.PrintRange.Selection:
        pages = sorted(set(selected_pages))
    elif mode == QPrinter.PrintRange.PageRange:
        ranges = printer.pageRanges()
        if not ranges.isEmpty():
            pages = [p for p in range(doc.page_count) if ranges.contains(p + 1)]
        else:
            first = max(1, printer.fromPage())
            last = printer.toPage() or doc.page_count
            pages = list(range(first - 1, min(last, doc.page_count)))
    else:
        pages = list(range(doc.page_count))
    pages = [p for p in pages if 0 <= p < doc.page_count]
    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        pages.reverse()
    # La mayoría de los controladores gestionan las copias. Evitar duplicarlas.
    if not printer.supportsMultipleCopies():
        copies = max(1, printer.copyCount())
        pages = pages * copies if printer.collateCopies() else [p for p in pages for _ in range(copies)]
    return pages


def print_pdf(doc: fitz.Document, printer: QPrinter, current_page: int,
              selected_pages: list[int]) -> None:
    pages = print_page_indices(doc, printer, current_page, selected_pages)
    if not pages:
        raise ValueError("No hay páginas para imprimir en la selección indicada.")
    # El origen del pintor queda en el área imprimible, sin sumar dos veces los márgenes.
    printer.setFullPage(False)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("No se pudo iniciar la impresión. Revisá la impresora seleccionada.")
    try:
        for i, pno in enumerate(pages):
            if i and not printer.newPage():
                raise RuntimeError("La impresora no pudo recibir la siguiente página.")
            pm = render_bounded_pixmap(doc[pno], dpi=printer.resolution(), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
            area = printer.pageRect(QPrinter.Unit.DevicePixel)
            scale = min(area.width() / img.width(), area.height() / img.height())
            w, h = img.width() * scale, img.height() * scale
            target = QRectF((area.width() - w) / 2, (area.height() - h) / 2, w, h)
            painter.drawImage(target, img)
        if not painter.end():
            raise RuntimeError("El controlador no pudo finalizar el trabajo de impresión.")
    except Exception:
        printer.abort()
        raise
    finally:
        if painter.isActive():
            painter.end()
