import os
import fitz
import pytest
from app.content_ops import find_text_block_at, replace_text_block, detect_card_border


def test_edit_text_never_erases_adjacent_lines_or_draws_border():
    """Verifica que editar un bloque de texto en una caja oscura o coloreada
    no borre las líneas adyacentes ni dibuje recuadros negros artificiales."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    # Fondo oscuro / verde similar al del caso reportado
    bg_shape = page.new_shape()
    bg_shape.draw_rect(fitz.Rect(20, 20, 380, 150))
    bg_shape.finish(color=(0.02, 0.16, 0.11), fill=(0.02, 0.16, 0.11))
    bg_shape.commit()

    # Línea 1 (título en negrita)
    page.insert_textbox(
        fitz.Rect(30, 30, 250, 48),
        "La Magia del Envoltorio:",
        fontsize=10,
        fontname="hebo",
        color=(1, 1, 1),
    )
    # Línea 2 (código adyacente, muy pegado verticalmente)
    page.insert_textbox(
        fitz.Rect(30, 52, 350, 68),
        "certificado = new FirmaDigitalDecorator(certificado);",
        fontsize=9,
        fontname="cour",
        color=(0.4, 0.9, 0.5),
    )
    # Línea 3 (descripción)
    page.insert_textbox(
        fitz.Rect(30, 72, 360, 88),
        "La misma variable polimórfica certificado se reasigna envolviéndose.",
        fontsize=8,
        fontname="helv",
        color=(0.8, 0.8, 0.8),
    )

    # Buscar bloque de la línea 1
    blk = find_text_block_at(page, fitz.Point(50, 35))
    assert blk is not None
    assert blk["text"] == "La Magia del Envoltorio:"
    assert blk.get("card_border") is None, "No debe detectar un card_border falso sobre fondo oscuro"

    drawings_before = len(page.get_drawings())

    # Reemplazar la línea 1
    replace_text_block(
        doc,
        0,
        blk["bbox"],
        "La Magia del Envoltori o:",
        fontsize=blk["fontsize"],
        fontname=blk["fontname"],
        color=blk["color"],
        fill_color=blk["fill_color"],
        card_border=blk.get("card_border"),
    )

    text_after = page.get_text()
    assert "La Magia del Envoltori o:" in text_after
    assert "certificado = new FirmaDigitalDecorator(certificado);" in text_after
    assert "La misma variable polimórfica certificado se reasigna" in text_after

    # No se deben haber agregado dibujos con contorno negro artificial
    for d in page.get_drawings():
        color = d.get("color")
        if color is not None:
            # Comprobar que no hay trazos oscuros espurios de (0.12, 0.12, 0.12)
            assert not (abs(color[0] - 0.12) < 0.01 and abs(color[1] - 0.12) < 0.01 and abs(color[2] - 0.12) < 0.01)

    doc.close()


def test_real_target_pdf_edit_if_present():
    """Si el archivo real del usuario existe en la ruta, valida el reemplazo exacto."""
    pdf_path = r"G:\Mi unidad\Ingenieria de software\2 parcial\Guia_iPhone_17_ProMax_Parcial2.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip("PDF de prueba no disponible en esta máquina")

    doc = fitz.open(pdf_path)
    page = doc[6]
    blk = find_text_block_at(page, fitz.Point(50, 680))
    assert blk is not None
    assert "Magia" in blk["text"]
    assert blk.get("card_border") is None

    replace_text_block(
        doc,
        6,
        blk["bbox"],
        "La Magia del Envoltori o:",
        fontsize=blk["fontsize"],
        fontname=blk["fontname"],
        color=blk["color"],
        fill_color=blk["fill_color"],
        card_border=blk.get("card_border"),
    )

    text_after = doc[6].get_text()
    assert "La Magia del Envoltori o:" in text_after
    assert "certificado = new FirmaDigitalDecorator(certificado);" in text_after
    assert "La misma variable polimórfica certificado se reasigna" in text_after
    doc.close()


def test_edit_tightly_spaced_lines_never_clips_line_above():
    """Verifica que editar una palabra en una línea inferior no corte letras de la línea superior
    cuando las métricas tipográficas (cajas de fuentes) se tocan o solapan ligeramente."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    # Línea 1 (título arriba)
    page.insert_textbox(
        fitz.Rect(50, 30, 350, 65),
        "Patrones GoF:",
        fontsize=16,
        fontname="hebo",
        color=(1, 1, 1),
    )
    # Línea 2 (palabras en la misma línea con ascender tocando la línea 1)
    page.insert_textbox(
        fitz.Rect(50, 64, 150, 95),
        "Decorator",
        fontsize=16,
        fontname="hebo",
        color=(0, 0.8, 1),
    )
    page.insert_textbox(
        fitz.Rect(155, 64, 185, 95),
        "&",
        fontsize=16,
        fontname="hebo",
        color=(1, 1, 1),
    )
    page.insert_textbox(
        fitz.Rect(190, 64, 290, 95),
        "Adapter",
        fontsize=16,
        fontname="hebo",
        color=(0, 1, 0.5),
    )

    # Buscar el bloque '&'
    blk = find_text_block_at(page, fitz.Point(160, 75))
    assert blk is not None
    assert blk["text"] == "&"

    # Reemplazar '&' por 'y'
    replace_text_block(
        doc,
        0,
        blk["bbox"],
        "y",
        fontsize=blk["fontsize"],
        fontname=blk["fontname"],
        color=blk["color"],
        fill_color=blk["fill_color"],
    )

    text_after = page.get_text()
    assert "Patrones GoF:" in text_after, "La línea superior 'Patrones GoF:' fue recortada"
    assert "Decorator" in text_after, "'Decorator' fue borrado"
    assert "Adapter" in text_after, "'Adapter' fue borrado"
    doc.close()


def test_real_target_pdf_page_0_ampersand_replacement_if_present():
    """Valida el caso real reportado: reemplazar '&' por 'y' en la portada de la guía."""
    pdf_path = r"G:\Mi unidad\Ingenieria de software\2 parcial\Guia_iPhone_17_ProMax_Parcial2.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip("PDF de prueba no disponible en esta máquina")

    doc = fitz.open(pdf_path)
    page = doc[0]
    blk = find_text_block_at(page, fitz.Point(228, 75))
    assert blk is not None
    assert blk["text"] == "&"

    replace_text_block(
        doc,
        0,
        blk["bbox"],
        "y",
        fontsize=blk["fontsize"],
        fontname=blk["fontname"],
        color=blk["color"],
        fill_color=blk["fill_color"],
    )

    text_after = doc[0].get_text()
    assert "Patrones GoF:" in text_after, "La línea 'Patrones GoF:' fue mutilada a 'Patro  GoF:'"
    assert "Decorator" in text_after
    assert "Adapter" in text_after
    doc.close()
