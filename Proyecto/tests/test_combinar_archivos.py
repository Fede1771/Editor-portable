"""Pruebas unitarias de combinación de archivos PDF e imágenes."""
from pathlib import Path
import pymupdf as fitz
import pytest

from app import creation


def test_combinar_multiples_pdfs(tmp_path):
    p1 = tmp_path / "a.pdf"
    p2 = tmp_path / "b.pdf"
    with fitz.open() as d1:
        d1.new_page().insert_text((50, 50), "PAGINA 1")
        d1.save(str(p1))
    with fitz.open() as d2:
        d2.new_page().insert_text((50, 50), "PAGINA 2")
        d2.save(str(p2))

    doc = creation.build_pdf([str(p1), str(p2)], bookmarks=True)
    assert doc.page_count == 2
    toc = doc.get_toc()
    assert len(toc) == 2
    assert toc[0][1] == "a"
    assert toc[1][1] == "b"
    doc.close()


def test_combinar_pdf_con_imagenes(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    with fitz.open() as d:
        d.new_page().insert_text((50, 50), "TEXTO")
        d.save(str(pdf_path))

    # Crear imagen sintética
    img_path = tmp_path / "img.png"
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), 0)
    pix.clear_with(0xFF0000)
    pix.save(str(img_path))

    doc = creation.build_pdf([str(pdf_path), str(img_path)], image_mode="a4", bookmarks=False)
    assert doc.page_count == 2
    doc.close()


def test_combinar_rechaza_lista_vacia():
    with pytest.raises(ValueError, match="No hay archivos"):
        creation.build_pdf([])


def test_combinar_clasifica_solo_pdf_e_imagenes():
    assert creation.classify("archivo.pdf") == "pdf"
    assert creation.classify("foto.PNG") == "image"
    assert creation.classify("foto.jpg") == "image"
    assert creation.classify("doc.docx") is None
    assert creation.classify("planilla.xlsx") is None
