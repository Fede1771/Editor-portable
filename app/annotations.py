"""
Módulo para gestión de comentarios, anotaciones de estudio y tinta (firma/lápiz).
"""
from typing import Any
import pymupdf as fitz


def get_all_comments_and_annots(doc: fitz.Document) -> list[dict[str, Any]]:
    """Extrae todos los comentarios y anotaciones embebidas en el documento.

    Retorna una lista de diccionarios con metadatos, autor, contenido y posición.
    """
    items = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for annot in page.annots():
            info = annot.info or {}
            annot_type_name = annot.type[1] if isinstance(annot.type, tuple) else str(annot.type)
            content = (info.get("content") or "").strip()
            subject = (info.get("subject") or "").strip()
            author = (info.get("title") or "").strip()
            
            # Si es resaltado/subrayado y no tiene content, intentar recuperar el texto bajo el área
            if not content and annot_type_name in ("Highlight", "Underline", "StrikeOut"):
                try:
                    content = page.get_text("text", clip=annot.rect).strip()
                except Exception:
                    pass

            items.append({
                "page": page_idx,
                "type": annot_type_name,
                "author": author or "Sin autor",
                "content": content or subject or f"Anotación {annot_type_name}",
                "rect": annot.rect,
                "color": annot.colors.get("stroke") or annot.colors.get("fill") or (1, 1, 0),
                "date": info.get("modDate") or info.get("creationDate") or "",
            })
    return items


def add_ink_annotation(
    doc: fitz.Document,
    page_idx: int,
    stroke_list: list[list[tuple[float, float]]],
    color: tuple[float, float, float] = (0.0, 0.2, 0.8),
    width: float = 2.0,
    author: str = "Firma",
) -> None:
    """Añade un trazo de tinta manuscrita (firma o lápiz libre) a la página."""
    if not stroke_list:
        return
    page = doc[page_idx]
    annot = page.add_ink_annot(stroke_list)
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    annot.set_info(title=author, content="Trazo / Firma manuscrita")
    annot.update()


def add_note_annotation(
    doc: fitz.Document,
    page_idx: int,
    point: fitz.Point,
    text: str,
    author: str = "Usuario",
    icon: str = "Comment",
    color: tuple[float, float, float] = (1.0, 0.8, 0.0),
) -> None:
    """Añade una nota adhesiva / comentario flotante en una coordenada."""
    if not text.strip():
        return
    page = doc[page_idx]
    annot = page.add_text_annot(point, text, icon=icon)
    annot.set_colors(stroke=color)
    annot.set_info(title=author, content=text)
    annot.update()


def add_highlight_annotation(
    doc: fitz.Document,
    page_idx: int,
    quads_or_rects: list[fitz.Rect | fitz.Quad],
    author: str = "Usuario",
    comment: str = "",
    color: tuple[float, float, float] = (1.0, 0.9, 0.0),
) -> None:
    """Añade un resaltado fluorescente sobre los rectángulos seleccionados."""
    if not quads_or_rects:
        return
    page = doc[page_idx]
    for r in quads_or_rects:
        annot = page.add_highlight_annot(r)
        annot.set_colors(stroke=color)
        if comment:
            annot.set_info(title=author, content=comment)
        annot.update()


def add_underline_annotation(
    doc: fitz.Document,
    page_idx: int,
    quads_or_rects: list[fitz.Rect | fitz.Quad],
    author: str = "Usuario",
    color: tuple[float, float, float] = (0.0, 0.45, 0.9),
) -> None:
    """Añade subrayado sobre las palabras o rectángulos seleccionados."""
    if not quads_or_rects:
        return
    page = doc[page_idx]
    for r in quads_or_rects:
        annot = page.add_underline_annot(r)
        annot.set_colors(stroke=color)
        annot.set_info(title=author)
        annot.update()


def add_strikeout_annotation(
    doc: fitz.Document,
    page_idx: int,
    quads_or_rects: list[fitz.Rect | fitz.Quad],
    author: str = "Usuario",
    color: tuple[float, float, float] = (0.9, 0.1, 0.1),
) -> None:
    """Añade tachado sobre las palabras o rectángulos seleccionados."""
    if not quads_or_rects:
        return
    page = doc[page_idx]
    for r in quads_or_rects:
        annot = page.add_strikeout_annot(r)
        annot.set_colors(stroke=color)
        annot.set_info(title=author)
        annot.update()


def delete_annotation_at(
    doc: fitz.Document,
    page_idx: int,
    point: fitz.Point,
    tolerance: float = 6.0,
) -> bool:
    """Elimina la anotación sobre la que se hizo clic."""
    page = doc[page_idx]
    for annot in page.annots():
        rect = annot.rect
        expanded = fitz.Rect(rect.x0 - tolerance, rect.y0 - tolerance, rect.x1 + tolerance, rect.y1 + tolerance)
        if expanded.contains(point):
            page.delete_annot(annot)
            return True
    return False
