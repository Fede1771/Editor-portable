"""Operaciones sobre páginas (fase 2). Funciones puras sobre documentos PyMuPDF."""
from __future__ import annotations

import math
import os
import re

import pymupdf as fitz

POSITIONS = {
    "Arriba a la izquierda": ("top", "left"),
    "Arriba al centro": ("top", "center"),
    "Arriba a la derecha": ("top", "right"),
    "Abajo a la izquierda": ("bottom", "left"),
    "Abajo al centro": ("bottom", "center"),
    "Abajo a la derecha": ("bottom", "right"),
}


# ----------------------------------------------------------------- utilidades
def parse_ranges(text: str, total: int) -> list[int]:
    """'1-3, 5, 8-' -> índices 0-based. Lanza ValueError si el texto no es válido."""
    pages: list[int] = []
    for part in re.split(r"[,;]", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"Rango no válido: '{part}'")
        if a < 1 or b > total or a > b:
            raise ValueError(f"Rango fuera de los límites (1-{total}): '{part}'")
        pages.extend(range(a - 1, b))
    if not pages:
        raise ValueError("No se indicó ninguna página.")
    return sorted(set(pages))


def _safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", text).strip(" .")
    return text[:60] or "parte"


def _groups_of_consecutive(pages: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for p in sorted(set(pages)):
        if groups and p == groups[-1][-1] + 1:
            groups[-1].append(p)
        else:
            groups.append([p])
    return groups


# ---------------------------------------------------------- organizar páginas
def delete_pages(doc: fitz.Document, pages: list[int]) -> None:
    pages = sorted(set(pages))
    if len(pages) >= doc.page_count:
        raise ValueError("No se pueden eliminar todas las páginas del documento.")
    doc.delete_pages(pages)


def rotate_pages(doc: fitz.Document, pages: list[int], angle: int) -> None:
    for p in pages:
        page = doc[p]
        page.set_rotation((page.rotation + angle) % 360)


def duplicate_pages(doc: fitz.Document, pages: list[int]) -> None:
    for offset, p in enumerate(sorted(set(pages))):
        src = p + offset
        doc.fullcopy_page(src, src + 1 if src + 1 < doc.page_count else -1)


def insert_blank(doc: fitz.Document, at: int, like: int | None = None) -> None:
    ref = doc[min(like if like is not None else max(0, at - 1), doc.page_count - 1)].rect
    doc.new_page(pno=at, width=ref.width, height=ref.height)


def insert_from_file(doc: fitz.Document, src_path: str, at: int) -> int:
    with fitz.open(src_path) as src:
        if src.needs_pass:
            raise ValueError("El archivo de origen está protegido con contraseña.")
        if not src.is_pdf:
            with fitz.open("pdf", src.convert_to_pdf()) as converted:
                doc.insert_pdf(converted, start_at=at)
                return converted.page_count
        doc.insert_pdf(src, start_at=at)
        return src.page_count


def replace_pages(doc: fitz.Document, pages: list[int], src_path: str, src_first: int) -> None:
    pages = sorted(set(pages))
    with fitz.open(src_path) as src:
        if src.needs_pass:
            raise ValueError("El archivo de origen está protegido con contraseña.")
        if src_first < 0 or src_first + len(pages) > src.page_count:
            raise ValueError(
                f"El origen tiene {src.page_count} páginas y se necesitan {len(pages)} "
                f"a partir de la {src_first + 1}."
            )
        for j, idx in enumerate(pages):
            doc.insert_pdf(src, from_page=src_first + j, to_page=src_first + j, start_at=idx)
            doc.delete_page(idx + 1)


def extract_pages(doc: fitz.Document, pages: list[int], out_path: str) -> None:
    from .document_io import selected_copy, save_pdf
    with selected_copy(doc, sorted(set(pages))) as new:
        save_pdf(new, out_path, garbage=3, deflate=True)


def reorder(doc: fitz.Document, order: list[int]) -> None:
    doc.select(order)


def move_order(total: int, pages: list[int], direction: int) -> list[int] | None:
    """Devuelve el nuevo orden tras mover `pages` una posición (±1), o None si no se puede."""
    sel = sorted(set(pages))
    order = list(range(total))
    if direction < 0:
        if sel[0] == 0:
            return None
        for p in sel:
            order[p - 1], order[p] = order[p], order[p - 1]
    else:
        if sel[-1] == total - 1:
            return None
        for p in reversed(sel):
            order[p + 1], order[p] = order[p], order[p + 1]
    return order


# ------------------------------------------------------------------- dividir
def _collision_free_path(path: str) -> str:
    """Evita la sobrescritura no deseada de archivos existentes."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    cnt = 1
    while os.path.exists(f"{base} ({cnt}){ext}"):
        cnt += 1
    return f"{base} ({cnt}){ext}"


def _save_part(doc: fitz.Document, pages: list[int], path: str) -> None:
    extract_pages(doc, pages, path)


def split_every(doc: fitz.Document, n: int, out_dir: str, base: str) -> list[str]:
    if n < 1:
        raise ValueError("El número de páginas por parte debe ser al menos 1.")
    paths = []
    for k, start in enumerate(range(0, doc.page_count, n), 1):
        pages = list(range(start, min(start + n, doc.page_count)))
        path = _collision_free_path(os.path.join(out_dir, f"{base}_parte{k:02d}.pdf"))
        _save_part(doc, pages, path)
        paths.append(path)
    return paths


def split_ranges(doc: fitz.Document, text: str, out_dir: str, base: str) -> list[str]:
    paths = []
    for k, chunk in enumerate([c for c in re.split(r"[;|]", text) if c.strip()], 1):
        pages = parse_ranges(chunk, doc.page_count)
        path = _collision_free_path(os.path.join(out_dir, f"{base}_parte{k:02d}.pdf"))
        _save_part(doc, pages, path)
        paths.append(path)
    if not paths:
        raise ValueError("No se indicó ningún rango. Separá las partes con ';' (ej: 1-3; 4-6).")
    return paths


def split_by_bookmarks(doc: fitz.Document, out_dir: str, base: str) -> list[str]:
    starts: list[tuple[int, str]] = []
    for level, title, page in doc.get_toc(simple=True):
        if level == 1 and page >= 1 and (not starts or starts[-1][0] != page - 1):
            starts.append((page - 1, title))
    if not starts:
        raise ValueError("El documento no tiene marcadores de primer nivel.")
    if starts[0][0] > 0:
        starts.insert(0, (0, "inicio"))
    paths = []
    for k, (start, title) in enumerate(starts, 1):
        end = starts[k][0] if k < len(starts) else doc.page_count
        if end <= start:
            continue
        path = _collision_free_path(os.path.join(out_dir, f"{base}_{k:02d}_{_safe_name(title)}.pdf"))
        _save_part(doc, list(range(start, end)), path)
        paths.append(path)
    return paths


# --------------------------------------------------------------------- recorte
def crop_pages(doc: fitz.Document, pages: list[int], left: float, top: float,
               right: float, bottom: float) -> None:
    """Recorta márgenes (en puntos) vistos desde la orientación en pantalla."""
    for p in pages:
        page = doc[p]
        view = page.rect
        new_view = fitz.Rect(view.x0 + left, view.y0 + top, view.x1 - right, view.y1 - bottom)
        if new_view.is_empty or new_view.width < 20 or new_view.height < 20:
            raise ValueError(f"Los márgenes son demasiado grandes para la página {p + 1}.")
        raw = new_view * page.derotation_matrix
        raw.normalize()
        base = page.cropbox
        raw = fitz.Rect(raw.x0 + base.x0, raw.y0 + base.y0, raw.x1 + base.x0, raw.y1 + base.y0)
        page.set_cropbox(raw & page.mediabox)


# ----------------------------------------------- texto superpuesto / fondo
def _draw_text(page: fitz.Page, view_pt: fitz.Point, text: str, size: float,
               color: tuple, opacity: float, angle: float = 0.0, overlay: bool = True) -> None:
    """Dibuja `text` con la esquina inferior izquierda en `view_pt` (coords en pantalla).

    `angle` es antihorario en grados, medido sobre lo que se ve en pantalla.
    """
    rot = page.rotation
    pt = fitz.Point(view_pt) * page.derotation_matrix
    raw_angle = angle + rot
    morph = (pt, fitz.Matrix(raw_angle)) if abs(raw_angle) > 1e-6 else None
    page.insert_text(pt, text, fontsize=size, fontname="helv", color=color,
                     fill_opacity=opacity, morph=morph, overlay=overlay)


def add_watermark(doc: fitz.Document, pages: list[int], text: str, size: float,
                  color: tuple, opacity: float, angle: float, behind: bool = False) -> None:
    if not text.strip():
        raise ValueError("El texto de la marca de agua está vacío.")
    length = fitz.get_text_length(text, fontname="helv", fontsize=size)
    a = math.radians(angle)
    direction = (math.cos(a), -math.sin(a))      # a lo largo del texto (y hacia abajo)
    perp = (math.sin(a), math.cos(a))            # "hacia abajo" respecto del texto
    for p in pages:
        page = doc[p]
        c = page.rect
        cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
        start = fitz.Point(
            cx - direction[0] * length / 2 + perp[0] * size * 0.35,
            cy - direction[1] * length / 2 + perp[1] * size * 0.35,
        )
        _draw_text(page, start, text, size, color, opacity, angle, overlay=not behind)


def add_header_footer(doc: fitz.Document, pages: list[int], template: str, position: str,
                      size: float, start_number: int, bates_digits: int,
                      color: tuple = (0, 0, 0)) -> None:
    if not template.strip():
        raise ValueError("El texto está vacío.")
    vertical, horizontal = POSITIONS[position]
    margin = 36.0
    total = doc.page_count
    for k, p in enumerate(pages):
        page = doc[p]
        n = start_number + k
        text = (template.replace("{n}", str(n)).replace("{total}", str(total))
                .replace("{bates}", str(n).zfill(bates_digits)))
        length = fitz.get_text_length(text, fontname="helv", fontsize=size)
        r = page.rect
        x = {"left": r.x0 + margin, "center": (r.x0 + r.x1 - length) / 2,
             "right": r.x1 - margin - length}[horizontal]
        y = r.y0 + margin if vertical == "top" else r.y1 - margin
        _draw_text(page, fitz.Point(x, y), text, size, color, 1.0)


def add_background(doc: fitz.Document, pages: list[int], color: tuple) -> None:
    for p in pages:
        page = doc[p]
        rect = (page.rect * page.derotation_matrix).normalize()
        page.draw_rect(rect, color=None, fill=color, overlay=False)


# ---------------------------------------------------- grillas / tablas
def detect_tables_on_page(page: fitz.Page) -> list[dict]:
    """Detecta tablas en una página usando PyMuPDF y extrae metadata de filas y columnas."""
    try:
        tabs = page.find_tables()
    except Exception:
        return []
    if not tabs or not tabs.tables:
        return []
    tables_data: list[dict] = []
    for t_idx, t in enumerate(tabs.tables):
        rows_data: list[dict] = []
        col_xs: set[float] = {round(t.bbox[0], 1), round(t.bbox[2], 1)}

        extracted: list[list[str]] = []
        try:
            extracted = t.extract()
        except Exception:
            extracted = []

        for r_idx, r in enumerate(t.rows):
            y_split = round(r.bbox[3], 1)
            if hasattr(r, "cells"):
                for cell in r.cells:
                    if cell:
                        col_xs.add(round(cell[0], 1))
                        col_xs.add(round(cell[2], 1))
            preview_cells: list[str] = []
            if r_idx < len(extracted):
                preview_cells = [str(c or "").strip() for c in extracted[r_idx] if str(c or "").strip()]
            preview = " | ".join(preview_cells[:3])
            if len(preview_cells) > 3:
                preview += "..."
            if not preview:
                preview = f"Fila {r_idx + 1}"
            rows_data.append({
                "row_index": r_idx,
                "bbox": (round(r.bbox[0], 1), round(r.bbox[1], 1), round(r.bbox[2], 1), round(r.bbox[3], 1)),
                "y_split": y_split,
                "preview": preview,
            })

        sorted_xs = sorted(col_xs)
        cleaned_xs = [sorted_xs[0]] if sorted_xs else []
        for x in sorted_xs[1:]:
            if abs(x - cleaned_xs[-1]) > 2.0:
                cleaned_xs.append(x)

        tables_data.append({
            "index": t_idx,
            "bbox": (round(t.bbox[0], 1), round(t.bbox[1], 1), round(t.bbox[2], 1), round(t.bbox[3], 1)),
            "row_count": t.row_count,
            "col_count": t.col_count,
            "rows": rows_data,
            "column_xs": cleaned_xs,
        })
    return tables_data


def expand_table_row(
    doc: fitz.Document,
    page_num: int,
    y_split: float,
    delta_y: float,
    *,
    table_bbox: tuple[float, float, float, float] | None = None,
    column_xs: list[float] | None = None,
    extend_borders: bool = True,
    expand_page: bool = True,
    border_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    border_width: float = 1.0,
) -> None:
    """Amplía el alto de una fila o grilla en una página PDF desplazando el contenido inferior.

    Corta la página en la coordenada vertical `y_split`:
    - El contenido por encima de `y_split` permanece intacto.
    - Se inserta un espacio vertical de `delta_y` puntos.
    - Todo el contenido por debajo de `y_split` se desplaza hacia abajo `delta_y` puntos.
    - Si `extend_borders` es True, extiende las líneas verticales y añade el borde horizontal inferior.
    - Si `expand_page` es True, la altura de la página se amplía en `delta_y` para no perder margen inferior.
    """
    if not (0 <= page_num < doc.page_count):
        raise IndexError(f"Índice de página fuera de rango: {page_num + 1} de {doc.page_count}")
    if delta_y <= 0:
        raise ValueError("El incremento de altura debe ser mayor a 0 puntos.")

    page = doc[page_num]
    rect = page.rect
    w, h = rect.width, rect.height

    if not (0 < y_split < h):
        raise ValueError(f"La línea de corte ({y_split:.1f} pt) debe estar dentro de la altura de la página (0..{h:.1f} pt).")

    new_h = h + delta_y if expand_page else h
    links = page.get_links()

    temp_doc = fitz.open()
    try:
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        new_page = doc.new_page(pno=page_num + 1, width=w, height=new_h)

        # Slice superior: desde 0 hasta y_split
        top_clip = fitz.Rect(0, 0, w, y_split)
        new_page.show_pdf_page(top_clip, temp_doc, 0, clip=top_clip)

        # Slice inferior: desde y_split hacia abajo, desplazado en delta_y
        bottom_source_h = h if expand_page else max(y_split, h - delta_y)
        bottom_source = fitz.Rect(0, y_split, w, bottom_source_h)
        bottom_target = fitz.Rect(0, y_split + delta_y, w, h + delta_y if expand_page else h)
        new_page.show_pdf_page(bottom_target, temp_doc, 0, clip=bottom_source)

        # Extensión de bordes vectoriales de la tabla en el nuevo espacio
        if extend_borders:
            xs: set[float] = set(column_xs or [])
            if table_bbox:
                xs.add(table_bbox[0])
                xs.add(table_bbox[2])
            if xs:
                sorted_xs = sorted(xs)
                cleaned_xs = [sorted_xs[0]]
                for x in sorted_xs[1:]:
                    if abs(x - cleaned_xs[-1]) > 1.5:
                        cleaned_xs.append(x)

                shape = new_page.new_shape()
                for x in cleaned_xs:
                    shape.draw_line(fitz.Point(x, y_split), fitz.Point(x, y_split + delta_y))
                min_x = cleaned_xs[0]
                max_x = cleaned_xs[-1]
                shape.draw_line(fitz.Point(min_x, y_split + delta_y), fitz.Point(max_x, y_split + delta_y))
                shape.finish(color=border_color, width=border_width)
                shape.commit()

        # Desplazamiento de enlaces
        for l in links:
            l_copy = dict(l)
            r = fitz.Rect(l.get("from", [0, 0, 0, 0]))
            if r.y0 >= y_split:
                l_copy["from"] = fitz.Rect(r.x0, r.y0 + delta_y, r.x1, r.y1 + delta_y)
                new_page.insert_link(l_copy)
            elif r.y1 <= y_split:
                new_page.insert_link(l_copy)

        doc.delete_page(page_num)
    finally:
        temp_doc.close()

