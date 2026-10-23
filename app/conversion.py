"""Conversión de documentos PDF a otros formatos (fase 6): Word, Excel, Imágenes, Texto, HTML."""
from __future__ import annotations

import os
import tempfile
from typing import Sequence

import pymupdf as fitz


def _safe_excel_cell(val: object | None) -> str:
    """Previene inyecciones de fórmulas maliciosas en Excel (CSV/formula injection)."""
    if val is None:
        return ""
    s = str(val)
    if s.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + s
    return s


def convert_to_word(doc: fitz.Document, out_docx_path: str, src_path: str | None = None) -> None:
    """Convierte el documento PDF en vivo a Microsoft Word (.docx)."""
    from pdf2docx import Converter
    from .privacy import TempManager

    fd, temp_pdf = TempManager.create_temp_file(prefix="pdf_word_", suffix=".pdf")
    os.close(fd)
    doc.save(temp_pdf, garbage=3, deflate=True)
    try:
        cv = Converter(temp_pdf)
        cv.convert(out_docx_path)
        cv.close()
    finally:
        TempManager.cleanup_path(temp_pdf)


def convert_to_excel(doc: fitz.Document, out_xlsx_path: str) -> int:
    """Extrae tablas del PDF y las guarda en un libro de Microsoft Excel (.xlsx).

    Retorna la cantidad total de tablas extraídas.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    # Eliminar hoja por defecto
    default_sheet = wb.active

    total_tables = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        tabs = page.find_tables()
        for t_idx, table in enumerate(tabs):
            total_tables += 1
            sheet_title = f"Pág {pno + 1} Tab {t_idx + 1}"[:31]
            ws = wb.create_sheet(title=sheet_title)
            for row in table.extract():
                ws.append([_safe_excel_cell(cell) for cell in row])

    # Si no se detectaron tablas tabuladas estructuradas, exportar líneas de texto por renglón
    if total_tables == 0:
        ws = wb.create_sheet(title="Contenido Texto")
        for pno in range(doc.page_count):
            ws.append([f"--- PÁGINA {pno + 1} ---"])
            for line in doc[pno].get_text("text").splitlines():
                if line.strip():
                    ws.append([_safe_excel_cell(line.strip())])

    if len(wb.sheetnames) > 1 and default_sheet in wb.worksheets:
        wb.remove(default_sheet)

    os.makedirs(os.path.dirname(os.path.abspath(out_xlsx_path)), exist_ok=True)
    wb.save(out_xlsx_path)
    return total_tables


def convert_to_images(
    doc: fitz.Document,
    out_dir: str,
    fmt: str = "png",
    dpi: int = 200,
    pages: Sequence[int] | None = None,
) -> list[str]:
    """Exporta las páginas del PDF como imágenes de alta resolución a una carpeta."""
    os.makedirs(out_dir, exist_ok=True)
    target_pages = list(pages) if pages is not None else list(range(doc.page_count))
    exported: list[str] = []

    ext = fmt.lower().replace(".", "")
    for pno in target_pages:
        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi)
        filename = f"pagina_{pno + 1:03d}.{ext}"
        out_path = os.path.join(out_dir, filename)
        pix.save(out_path)
        exported.append(out_path)

    return exported


def convert_to_text(doc: fitz.Document, out_txt_path: str) -> None:
    """Exporta el texto plano de todo el documento."""
    os.makedirs(os.path.dirname(os.path.abspath(out_txt_path)), exist_ok=True)
    with open(out_txt_path, "w", encoding="utf-8") as f:
        for pno in range(doc.page_count):
            f.write(f"--- PÁGINA {pno + 1} ---\n\n")
            f.write(doc[pno].get_text("text"))
            f.write("\n\n")


def convert_to_html(doc: fitz.Document, out_html_path: str) -> None:
    """Exporta el contenido del documento a formato HTML con estilos."""
    os.makedirs(os.path.dirname(os.path.abspath(out_html_path)), exist_ok=True)
    with open(out_html_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Documento Exportado</title>")
        f.write("<style>body{font-family:sans-serif;margin:40px;background:#f0f2f5;}.page{background:#fff;padding:30px;margin-bottom:30px;box-shadow:0 2px 6px rgba(0,0,0,0.15);}</style>")
        f.write("</head><body>\n")
        for pno in range(doc.page_count):
            f.write(f"<div class='page'><h3>Página {pno + 1}</h3>\n")
            f.write(doc[pno].get_text("html"))
            f.write("</div>\n")
        f.write("</body></html>")
