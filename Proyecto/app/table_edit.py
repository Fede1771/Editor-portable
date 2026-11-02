"""Edición vectorial de tablas: conservar el estilo y la identidad de la página."""
from __future__ import annotations

import math
import re

import pymupdf as fitz

EPS = 0.15


def visible_paths(page):
    """Recorta trazos a sus clips reales, también después de varias ediciones."""
    clips = {}
    result = []
    for path in page.get_drawings(extended=True):
        level = path.get("level", 0)
        clips = {k: v for k, v in clips.items() if k < level}
        if path["type"] == "clip":
            clips[level] = fitz.Rect(path["scissor"])
            continue
        if path["type"] == "group":
            continue
        clip = fitz.Rect(page.rect)
        for bounds in clips.values():
            clip &= bounds
        if clip.is_empty:
            continue
        items = []
        fills = []
        for item in path["items"]:
            segments = []
            if item[0] == "re":
                r = item[1]
                if path.get("fill") is not None:
                    rect = r & clip
                    if not rect.is_empty:
                        fills.append(("re", rect, item[2]))
                    if "s" not in path["type"]:
                        continue
                segments = [(r.tl, r.tr), (r.tr, r.br), (r.br, r.bl), (r.bl, r.tl)]
            elif item[0] == "l":
                segments = [(item[1], item[2])]
            elif clip.contains(path["rect"]):
                items.append(item)
            for a, b in segments:
                if abs(a.x - b.x) < EPS and clip.x0 - EPS <= a.x <= clip.x1 + EPS:
                    lo, hi = max(min(a.y, b.y), clip.y0), min(max(a.y, b.y), clip.y1)
                    if hi > lo + .01:
                        items.append(("l", fitz.Point(a.x, lo), fitz.Point(a.x, hi)))
                elif abs(a.y - b.y) < EPS and clip.y0 - EPS <= a.y <= clip.y1 + EPS:
                    lo, hi = max(min(a.x, b.x), clip.x0), min(max(a.x, b.x), clip.x1)
                    if hi > lo + .01:
                        items.append(("l", fitz.Point(lo, a.y), fitz.Point(hi, a.y)))
                elif clip.contains(a) and clip.contains(b):
                    items.append(("l", a, b))
        if fills:
            fill_path = dict(path, items=fills, type="f", color=None, width=None,
                             rect=path["rect"] & clip)
            result.append(fill_path)
        if items:
            copy = dict(path)
            if fills:
                copy.update(type="s", fill=None)
            copy["items"] = items
            r = path["rect"]
            copy["rect"] = fitz.Rect(max(r.x0, clip.x0), max(r.y0, clip.y0),
                                     min(r.x1, clip.x1), min(r.y1, clip.y1))
            result.append(copy)
    return result


def _segments(paths):
    for path in paths:
        if path.get("color") is None or "s" not in path["type"]:
            continue
        for item in path["items"]:
            if item[0] == "l":
                yield item[1], item[2], path
            elif item[0] == "re":
                r = item[1]
                for a, b in [(r.tl, r.tr), (r.tr, r.br), (r.br, r.bl), (r.bl, r.tl)]:
                    yield a, b, path


def _fill_at(paths, point):
    color = (1, 1, 1)
    for path in paths:
        if path.get("fill") is not None and path["rect"].contains(point):
            color = path["fill"]
    return color


def _line(page, a, b, style):
    page.draw_line(a, b, color=style["color"], width=style.get("width") or .5,
                   dashes=style.get("dashes"), stroke_opacity=style.get("stroke_opacity", 1))


def _blank_row(page, paths, row, y0, y1, *, horizontal=False):
    """Extiende sólo las divisiones que existen en esta fila, no toda la tabla."""
    cells = [fitz.Rect(c) for c in row["cells"] if c]
    sample_y = (row["bbox"][1] + row["bbox"][3]) / 2
    for cell in cells:
        page.draw_rect(fitz.Rect(cell.x0, y0, cell.x1, y1), color=None,
                       fill=_fill_at(paths, fitz.Point((cell.x0 + cell.x1) / 2, sample_y)))
    bounds = fitz.Rect(row["bbox"])
    for a, b, style in _segments(paths):
        if abs(a.x - b.x) < EPS and min(a.y, b.y) <= sample_y <= max(a.y, b.y):
            if bounds.x0 - 2 <= a.x <= bounds.x1 + 2:
                _line(page, fitz.Point(a.x, y0), fitz.Point(a.x, y1), style)
    if horizontal:
        candidates = [(abs(a.y - bounds.y1), a, b, style) for a, b, style in _segments(paths)
                      if abs(a.y - b.y) < EPS and min(a.x, b.x) < bounds.x1
                      and max(a.x, b.x) > bounds.x0 and abs(a.y - bounds.y1) < 2]
        if candidates:
            _, a, b, style = min(candidates, key=lambda v: v[0])
            _line(page, fitz.Point(bounds.x0, y0), fitz.Point(bounds.x1, y0), style)


def _copy(target, source, clip, dest=None):
    clip = fitz.Rect(clip)
    dest = fitz.Rect(dest if dest is not None else clip)
    if clip.width > .01 and clip.height > .01 and dest.width > .01 and dest.height > .01:
        target.show_pdf_page(dest, source, 0, clip=clip, keep_proportion=False)


def _check_page(page):
    if page.rotation or page.cropbox_position != fitz.Point(0, 0):
        raise ValueError("La edición de tablas requiere una página sin rotación ni recorte desplazado.")


def _object_moves(page, split, delta):
    """Mover también enlaces, notas y formularios; nunca eliminar sus objetos."""
    moves = []
    for xref, kind_id, _ in page.annot_xrefs():
        if kind_id == fitz.PDF_ANNOT_POPUP:
            continue
        kind, raw = page.parent.xref_get_key(xref, "Rect")
        if kind != "array":
            continue
        coords = [float(n) for n in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", raw)]
        if len(coords) != 4:
            continue
        r = fitz.Rect(coords) * page.transformation_matrix
        if r.y0 < split - EPS < r.y1 or (delta < 0 and r.y1 > split + delta + EPS and r.y0 < split - EPS):
            raise ValueError("El borde elegido atraviesa una nota, enlace o formulario. Elegí otra fila.")
        if r.y0 >= split - EPS:
            moves.append(xref)
    return moves


def _commit(doc, pno, composed, moves=(), delta=0):
    """Sustituye contenido y recursos sin reemplazar el objeto Page ni sus referencias."""
    original = doc[pno]
    height_delta = composed.rect.height - original.rect.height
    for key in ("Contents", "Resources"):
        _, value = doc.xref_get_key(composed.xref, key)
        doc.xref_set_key(original.xref, key, value)
    targets = set(moves)
    if height_delta:
        targets.update(x for x, _, _ in original.annot_xrefs())
    for xref in targets:
        for key in ("Rect", "QuadPoints", "Vertices", "InkList", "L", "CL"):
            kind, value = doc.xref_get_key(xref, key)
            if kind != "array":
                continue
            index = 0
            def translate(match):
                nonlocal index
                index += 1
                offset = height_delta - (delta if xref in moves else 0)
                v = float(match.group()) + (offset if index % 2 == 0 else 0)
                return f"{v:.6f}"
            doc.xref_set_key(xref, key, re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", translate, value))
    if height_delta:
        original.set_mediabox(composed.rect)
    doc.delete_page(composed.number)
    doc.reload_page(doc[pno])


def edit_row(doc, pno, table, row_index, *, height=None, insert=None, expand_page=False, extend_borders=True):
    """Inserta una fila vacía o cambia su alto, manteniendo el tamaño de la página."""
    page = doc[pno]
    _check_page(page)
    row = table["rows"][row_index]
    bounds = fitz.Rect(row["bbox"])
    if any(c and (c[1] < bounds.y0 - 1 or c[3] > bounds.y1 + 1)
           for r in table["rows"] for c in r.get("cells", [])
           if c and c[1] < bounds.y1 - EPS and c[3] > bounds.y0 + EPS):
        raise ValueError("Esta fila tiene celdas combinadas verticalmente. Elegí una fila sin esa combinación.")
    if height is None:
        height = bounds.height
    if not math.isfinite(height) or height < 5 or height > 600:
        raise ValueError("El alto debe estar entre 5 y 600 puntos.")
    paths = visible_paths(page)
    if insert:
        split = bounds.y0 if insert == "above" else bounds.y1
        delta = height
    else:
        delta = height - bounds.height
        if abs(delta) < .05:
            return
        # El corte cae antes del borde horizontal, para trasladarlo una sola vez.
        split = bounds.y1 - 1.5
        words = page.get_text("words", clip=bounds)
        text_bottom = max((w[3] for w in words), default=bounds.y0)
        if bounds.y0 + height < text_bottom + 3:
            raise ValueError("Ese alto cortaría el texto. Aumentá el alto de la fila.")
    # El desplazamiento afecta el ancho completo de la página: proteger también
    # textos e imágenes situados al costado de la tabla.
    occupied = [fitz.Rect(w[:4]) for w in page.get_text("words")]
    occupied += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    for content in occupied:
        crosses = content.y0 + EPS < split < content.y1 - EPS
        removed = delta < 0 and content.y1 > split + delta + EPS and content.y0 < split - EPS
        if crosses or removed:
            raise ValueError("El cambio cortaría texto o una imagen junto a la tabla. Elegí otro borde o un alto mayor.")
    moves = _object_moves(page, split, delta)
    if delta > 0 and not expand_page:
        bottoms = [b[3] for b in page.get_text("blocks")]
        bottoms += [p["rect"].y1 for p in paths]
        bottoms += [i["bbox"][3] for i in page.get_image_info()]
        bottoms += [(fitz.Rect([float(n) for n in doc.xref_get_key(x, "Rect")[1].strip("[]").split()]) * page.transformation_matrix).y1
                    for x in moves]
        if max(bottoms, default=0) + delta > page.rect.height - 2:
            raise ValueError("No hay espacio suficiente al pie de la página. Reducí el alto para conservar el tamaño del PDF.")
    w, h = page.rect.width, page.rect.height
    new_h = h + delta if expand_page else h
    with fitz.open() as source:
        source.insert_pdf(doc, from_page=pno, to_page=pno)
        composed = doc.new_page(width=w, height=new_h)
        _copy(composed, source, (0, 0, w, split + min(delta, 0)))
        _copy(composed, source, (0, split, w, h if expand_page else h - max(delta, 0)),
              (0, split + delta, w, h + delta if expand_page else h + min(delta, 0)))
        if delta > 0:
            if extend_borders:
                _blank_row(composed, paths, row, split, split + delta, horizontal=bool(insert))
        _commit(doc, pno, composed, moves, delta)


def insert_column(doc, pno, table, column_index, *, before=False):
    """Agrega una columna vacía redistribuyendo el ancho de la tabla y sus celdas."""
    page = doc[pno]
    _check_page(page)
    bbox = fitz.Rect(table["bbox"])
    xs = table["column_xs"]
    width = xs[column_index + 1] - xs[column_index]
    factor = bbox.width / (bbox.width + width)
    extra = width * factor
    split = xs[column_index if before else column_index + 1]
    if min(b - a for a, b in zip(xs, xs[1:])) * factor < 12:
        raise ValueError("Las columnas quedarían demasiado angostas. Usá una tabla con más ancho disponible.")
    for xref, kind_id, _ in page.annot_xrefs():
        if kind_id == fitz.PDF_ANNOT_POPUP:
            continue
        kind, raw = doc.xref_get_key(xref, "Rect")
        if kind == "array" and (fitz.Rect([float(n) for n in raw.strip("[]").split()]) * page.transformation_matrix).intersects(bbox):
            raise ValueError("Esta tabla contiene una nota, enlace o formulario. Movelo fuera de la tabla antes de redistribuir columnas.")
    paths = visible_paths(page)
    cells = {tuple(c) for r in table["rows"] for c in r["cells"] if c}
    # Incluir el grosor exterior para no dejar restos de la grilla anterior.
    outer = fitz.Rect(bbox.x0 - 2, bbox.y0 - 2, bbox.x1 + 2, bbox.y1 + 2) & page.rect
    with fitz.open() as source:
        source.insert_pdf(doc, from_page=pno, to_page=pno)
        composed = doc.new_page(width=page.rect.width, height=page.rect.height)
        p = source[0].rect
        for clip in [(0, 0, p.width, outer.y0), (0, outer.y1, p.width, p.height),
                     (0, outer.y0, outer.x0, outer.y1), (outer.x1, outer.y0, p.width, outer.y1)]:
            _copy(composed, source, clip)
        for cell_tuple in sorted(cells, key=lambda c: (c[1], c[0])):
            cell = fitz.Rect(cell_tuple)
            merged = cell.width > width + 2
            covers = cell.x0 + EPS < split < cell.x1 - EPS
            covers |= merged and ((before and abs(cell.x0 - split) < EPS) or (not before and abs(cell.x1 - split) < EPS))
            left = bbox.x0 + (cell.x0 - bbox.x0) * factor
            right = bbox.x0 + (cell.x1 - bbox.x0) * factor
            if cell.x0 >= split - EPS and not (covers and before):
                left += extra
            if cell.x1 > split + EPS or covers:
                right += extra
            # Cada celda se copia completa: el texto de un encabezado combinado no se corta.
            clip = fitz.Rect(cell.x0 - .6, cell.y0 - .6, cell.x1 + .6, cell.y1 + .6) & outer
            padding = .6 * (right - left) / cell.width
            target = fitz.Rect(left - padding, cell.y0 - .6, right + padding, cell.y1 + .6)
            _copy(composed, source, clip, target)
            at_boundary = abs((cell.x0 if before else cell.x1) - split) < EPS
            if at_boundary and not covers:
                x0 = bbox.x0 + (split - bbox.x0) * factor
                new = fitz.Rect(x0, cell.y0, x0 + extra, cell.y1)
                fill = _fill_at(paths, fitz.Point((cell.x0 + cell.x1) / 2, (cell.y0 + cell.y1) / 2))
                composed.draw_rect(new, color=None, fill=fill)
                # Copiar estilos de los bordes de la celda contigua, no imponer negro.
                for a, b, style in _segments(paths):
                    if abs(a.y - b.y) < EPS and min(abs(a.y - cell.y0), abs(a.y - cell.y1)) < 1.2 and min(a.x,b.x) < cell.x1 and max(a.x,b.x) > cell.x0:
                        _line(composed, fitz.Point(new.x0, a.y), fitz.Point(new.x1, a.y), style)
                    elif abs(a.x - b.x) < EPS and abs(a.x - split) < 1.2 and min(a.y,b.y) <= cell.y0 + 2 and max(a.y,b.y) >= cell.y1 - 2:
                        _line(composed, fitz.Point(new.x0, cell.y0), fitz.Point(new.x0, cell.y1), style)
                        _line(composed, fitz.Point(new.x1, cell.y0), fitz.Point(new.x1, cell.y1), style)
        _commit(doc, pno, composed)


def delete_row(doc, pno, table, row_index):
    """Quita la fila y su contenido; sube el contenido inferior sin cambiar la página."""
    page = doc[pno]
    _check_page(page)
    if table["row_count"] <= 1:
        raise ValueError("La tabla debe conservar al menos una fila.")
    bounds = fitz.Rect(table["rows"][row_index]["bbox"])
    for row in table["rows"]:
        for cell in row["cells"]:
            if cell and cell[1] < bounds.y1 - EPS and cell[3] > bounds.y0 + EPS:
                if cell[1] < bounds.y0 - 1 or cell[3] > bounds.y1 + 1:
                    raise ValueError("No se puede eliminar una fila atravesada por celdas combinadas verticalmente.")
    content = [fitz.Rect(w[:4]) for w in page.get_text("words")]
    content += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    for rect in content:
        if rect.y1 > bounds.y0 + EPS and rect.y0 < bounds.y1 - EPS:
            if rect.x0 < bounds.x0 - 1 or rect.x1 > bounds.x1 + 1 or rect.y0 < bounds.y0 - 1 or rect.y1 > bounds.y1 + 1:
                raise ValueError("Hay contenido junto a la fila o atravesando su borde. No se puede eliminar sin recortarlo.")
    for path in visible_paths(page):
        rect = path["rect"]
        if rect.y1 > bounds.y0 + EPS and rect.y0 < bounds.y1 - EPS:
            if rect.x0 < bounds.x0 - 2 or rect.x1 > bounds.x1 + 2:
                raise ValueError("Hay gráficos junto a la fila. No se puede eliminar sin recortarlos.")
    delta = -bounds.height
    moves = _object_moves(page, bounds.y1, delta)
    w, h = page.rect.width, page.rect.height
    with fitz.open() as source:
        source.insert_pdf(doc, from_page=pno, to_page=pno)
        composed = doc.new_page(width=w, height=h)
        _copy(composed, source, (0, 0, w, bounds.y0))
        _copy(composed, source, (0, bounds.y1, w, h), (0, bounds.y0, w, h + delta))
        _commit(doc, pno, composed, moves, delta)


def delete_column(doc, pno, table, column_index):
    """Quita las celdas de una columna y distribuye las restantes en el mismo ancho."""
    page = doc[pno]
    _check_page(page)
    xs = table["column_xs"]
    if len(xs) <= 2:
        raise ValueError("La tabla debe conservar al menos una columna.")
    bbox = fitz.Rect(table["bbox"])
    left, right = xs[column_index:column_index + 2]
    width = right - left
    factor = bbox.width / (bbox.width - width)
    for xref, kind_id, _ in page.annot_xrefs():
        if kind_id == fitz.PDF_ANNOT_POPUP:
            continue
        kind, raw = doc.xref_get_key(xref, "Rect")
        if kind == "array" and (fitz.Rect([float(n) for n in raw.strip("[]").split()]) * page.transformation_matrix).intersects(bbox):
            raise ValueError("La tabla contiene una nota, enlace o formulario. Movelo fuera antes de eliminar columnas.")
    def mapped(x):
        return bbox.x0 + (x - bbox.x0 - min(width, max(0, x - left))) * factor
    outer = fitz.Rect(bbox.x0 - 2, bbox.y0 - 2, bbox.x1 + 2, bbox.y1 + 2) & page.rect
    cells = {tuple(c) for row in table["rows"] for c in row["cells"] if c}
    with fitz.open() as source:
        source.insert_pdf(doc, from_page=pno, to_page=pno)
        composed = doc.new_page(width=page.rect.width, height=page.rect.height)
        p = source[0].rect
        for clip in [(0, 0, p.width, outer.y0), (0, outer.y1, p.width, p.height),
                     (0, outer.y0, outer.x0, outer.y1), (outer.x1, outer.y0, p.width, outer.y1)]:
            _copy(composed, source, clip)
        for coords in sorted(cells, key=lambda c: (c[1], c[0])):
            cell = fitz.Rect(coords)
            if cell.x0 >= left - EPS and cell.x1 <= right + EPS:
                continue
            x0, x1 = mapped(cell.x0), mapped(cell.x1)
            if x1 - x0 < EPS:
                continue
            clip = fitz.Rect(cell.x0 - .6, cell.y0 - .6, cell.x1 + .6, cell.y1 + .6) & outer
            padding = .6 * (x1 - x0) / cell.width
            _copy(composed, source, clip, (x0 - padding, cell.y0 - .6, x1 + padding, cell.y1 + .6))
        _commit(doc, pno, composed)
