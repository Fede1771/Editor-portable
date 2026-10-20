"""Operaciones de edición de contenido (fase 4): texto, imágenes, redacción/censura y enlaces."""
from __future__ import annotations

import os
from typing import Sequence

import pymupdf as fitz


def add_text_box(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    text: str,
    fontsize: float = 12.0,
    fontname: str = "helv",
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Inserta un cuadro de texto en la página especificada."""
    page = doc[page_idx]
    # Si el rect es muy pequeño o un punto, crear un área por defecto hacia abajo a la derecha
    if rect.width < 10 or rect.height < 10:
        p_rect = page.rect
        w = max(150.0, min(300.0, p_rect.x1 - rect.x0 - 20))
        h = max(30.0, fontsize * 2.5)
        rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + w, rect.y0 + h)

    # Insertar texto dentro del rectángulo
    page.insert_textbox(
        rect,
        text,
        fontsize=fontsize,
        fontname=fontname,
        color=color,
        align=fitz.TEXT_ALIGN_LEFT,
    )


def apply_redaction(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    text: str = "",
) -> None:
    """Censura / redacta físicamente el área rectangular especificada."""
    page = doc[page_idx]
    page.add_redact_annot(rect, text=text, fill=fill_color)
    page.apply_redactions()


def redact_search_phrase(
    doc: fitz.Document,
    phrase: str,
    pages: Sequence[int] | None = None,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> int:
    """Busca una frase y redacta físicamente todas sus ocurrencias."""
    if not phrase.strip():
        return 0
    target_pages = pages if pages is not None else range(doc.page_count)
    total_matches = 0
    for pno in target_pages:
        page = doc[pno]
        matches = page.search_for(phrase)
        if matches:
            total_matches += len(matches)
            for r in matches:
                page.add_redact_annot(r, fill=fill_color)
            page.apply_redactions()
    return total_matches


def insert_image(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    image_path: str,
) -> None:
    """Inserta una imagen en el rectángulo especificado de la página."""
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"No existe el archivo de imagen: {image_path}")
    page = doc[page_idx]
    # Si el rect es muy pequeño, usar el tamaño proporcional de la imagen
    if rect.width < 10 or rect.height < 10:
        with fitz.open(image_path) as img_doc:
            p0 = img_doc[0]
            iw, ih = p0.rect.width, p0.rect.height
        scale = min(200.0 / max(iw, ih), 1.0)
        w, h = iw * scale, ih * scale
        rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + w, rect.y0 + h)
    page.insert_image(rect, filename=image_path)


def extract_images(
    doc: fitz.Document,
    out_dir: str,
    pages: Sequence[int] | None = None,
) -> list[str]:
    """Extrae todas las imágenes incrustadas de las páginas indicadas."""
    os.makedirs(out_dir, exist_ok=True)
    target_pages = pages if pages is not None else range(doc.page_count)
    extracted_paths: list[str] = []
    seen_xrefs: set[int] = set()

    for pno in target_pages:
        page = doc[pno]
        img_list = page.get_images(full=True)
        for img_idx, img_info in enumerate(img_list):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            out_name = f"pagina_{pno + 1:03d}_img_{img_idx + 1:02d}.{image_ext}"
            out_path = os.path.join(out_dir, out_name)
            with open(out_path, "wb") as f:
                f.write(image_bytes)
            extracted_paths.append(out_path)
    return extracted_paths


def add_hyperlink(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    uri: str = "",
    target_page: int | None = None,
) -> None:
    """Añade un vínculo clickable web (URI) o a una página interna."""
    page = doc[page_idx]
    if target_page is not None:
        link_dict = {
            "kind": fitz.LINK_GOTO,
            "from": rect,
            "page": max(0, min(doc.page_count - 1, target_page)),
        }
    else:
        link_dict = {
            "kind": fitz.LINK_URI,
            "from": rect,
            "uri": uri,
        }
    page.insert_link(link_dict)



def sample_visual_colors(
    page: fitz.Page, bbox: fitz.Rect
) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    """Muestrea los píxeles de la región para detectar color de texto, color de fondo y densidad de trazo."""
    try:
        pix = page.get_pixmap(clip=bbox, dpi=150)
        if pix.width < 2 or pix.height < 2:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.0

        from collections import Counter
        pixels = []
        for y in range(pix.height):
            for x in range(pix.width):
                r, g, b = pix.pixel(x, y)[:3]
                pixels.append((r, g, b))

        # El color más frecuente es el fondo
        bg_cand = Counter(pixels).most_common(1)[0][0]
        bg_r, bg_g, bg_b = bg_cand

        # Píxeles de texto: aquellos que difieren sustancialmente del fondo
        def dist_sq(p):
            return (p[0] - bg_r) ** 2 + (p[1] - bg_g) ** 2 + (p[2] - bg_b) ** 2

        text_pixels = [p for p in pixels if dist_sq(p) > 1600]
        density = len(text_pixels) / len(pixels)

        if text_pixels:
            text_pixels.sort(key=lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2])
            core = text_pixels[: max(1, len(text_pixels) // 2)]
            avg_r = sum(p[0] for p in core) / len(core) / 255.0
            avg_g = sum(p[1] for p in core) / len(core) / 255.0
            avg_b = sum(p[2] for p in core) / len(core) / 255.0

            lum = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b
            spread = max(avg_r, avg_g, avg_b) - min(avg_r, avg_g, avg_b)
            if lum < 0.22 and spread < 0.05:
                text_col = (0.0, 0.0, 0.0)
            else:
                text_col = (round(avg_r, 2), round(avg_g, 2), round(avg_b, 2))
        else:
            text_col = (0.0, 0.0, 0.0)

        bg_col = (round(bg_r / 255.0, 3), round(bg_g / 255.0, 3), round(bg_b / 255.0, 3))
        return text_col, bg_col, density
    except Exception:
        return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.0


def find_text_block_at(
    page: fitz.Page,
    point: fitz.Point,
    selection_rect: fitz.Rect | None = None,
) -> dict | None:
    """Detecta el recuadro, tarjeta o párrafo específico bajo el cursor y detecta automáticamente
    tipografía, estilo, tamaño y color (compatible tanto con PDFs nativos como con PDFs con OCR).
    """
    text_dict = page.get_text("dict")
    all_spans = []
    for b in text_dict.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text", "").strip()
                if t:
                    all_spans.append(span)

    if not all_spans:
        return None

    cluster = []
    # Caso 1: El usuario arrastró un recuadro de selección deliberado con el ratón
    if selection_rect is not None and selection_rect.width > 20 and selection_rect.height > 10:
        for s in all_spans:
            s_rect = fitz.Rect(s["bbox"])
            if selection_rect.intersects(s_rect):
                cluster.append(s)

    # Caso 2: Clic puntual: aislar la tarjeta / celda / bloque que contiene el punto
    if not cluster:
        target_span = None
        min_dist = float("inf")
        for s in all_spans:
            sb = fitz.Rect(s["bbox"])
            exp = fitz.Rect(sb.x0 - 4, sb.y0 - 4, sb.x1 + 4, sb.y1 + 4)
            if exp.contains(point):
                target_span = s
                break
            d = fitz.Point(point).distance_to(sb)
            if d < min_dist and d <= 18.0:
                min_dist = d
                target_span = s

        if target_span is None:
            return None

        card_x0, card_x1 = target_span["bbox"][0], target_span["bbox"][2]
        card_y0, card_y1 = target_span["bbox"][1], target_span["bbox"][3]

        # Expandir la tarjeta uniendo spans adyacentes horizontal y verticalmente
        # Dentro de una misma tarjeta el espacio vertical entre renglones es <= 5 pt
        changed = True
        while changed:
            changed = False
            for s in all_spans:
                sx0, sy0, sx1, sy1 = s["bbox"]
                horiz_overlap = max(card_x0 - 8, sx0) <= min(card_x1 + 8, sx1)
                vert_overlap = (sy0 <= card_y1 + 5.0) and (sy1 >= card_y0 - 5.0)
                if horiz_overlap and vert_overlap:
                    if sx0 < card_x0:
                        card_x0 = sx0
                        changed = True
                    if sx1 > card_x1:
                        card_x1 = sx1
                        changed = True
                    if sy0 < card_y0:
                        card_y0 = sy0
                        changed = True
                    if sy1 > card_y1:
                        card_y1 = sy1
                        changed = True

        cluster = [
            s for s in all_spans
            if (s["bbox"][0] >= card_x0 - 4 and s["bbox"][2] <= card_x1 + 4)
            and (s["bbox"][1] >= card_y0 - 4 and s["bbox"][3] <= card_y1 + 4)
        ]

    if not cluster:
        return None

    # Agrupar spans por líneas (mismo rango de Y)
    lines_map: list[list[dict]] = []
    for s in sorted(cluster, key=lambda s: (s["bbox"][1], s["bbox"][0])):
        placed = False
        for line in lines_map:
            avg_y = sum(x["bbox"][1] for x in line) / len(line)
            if abs(s["bbox"][1] - avg_y) <= 5.0:
                line.append(s)
                placed = True
                break
        if not placed:
            lines_map.append([s])

    lines_map.sort(key=lambda l: min(x["bbox"][1] for x in l))
    lines_text = []
    for l in lines_map:
        l.sort(key=lambda x: x["bbox"][0])
        line_str = " ".join(x["text"].strip() for x in l if x["text"].strip())
        if line_str:
            lines_text.append(line_str)

    full_text = "\n".join(lines_text).strip()
    if not full_text:
        return None

    bbox = fitz.Rect(
        min(s["bbox"][0] for s in cluster),
        min(s["bbox"][1] for s in cluster),
        max(s["bbox"][2] for s in cluster),
        max(s["bbox"][3] for s in cluster),
    )

    s0 = cluster[0]
    num_lines = max(1, len(lines_map))
    avg_line_height = bbox.height / num_lines
    visual_fs = round(avg_line_height * 0.78, 1)

    # 1. Detección automática del color (PDF nativo vs muestreo visual)
    sampled_text_col, sampled_bg_col, stroke_density = sample_visual_colors(page, bbox)
    raw_col = s0.get("color", 0)
    if isinstance(raw_col, int) and raw_col != 0:
        r = ((raw_col >> 16) & 0xFF) / 255.0
        g = ((raw_col >> 8) & 0xFF) / 255.0
        b_c = (raw_col & 0xFF) / 255.0
        font_color = (round(r, 2), round(g, 2), round(b_c, 2))
    else:
        font_color = sampled_text_col

    # 2. Detección automática del tamaño de fuente
    raw_fs = s0.get("size", 10.0)
    raw_fn = s0.get("font", "").lower()
    is_ocr = ("glyphless" in raw_fn) or ("tess" in raw_fn)
    is_corrupt_size = (raw_fs < 3.0) or (raw_fs > 120.0)

    if is_ocr or is_corrupt_size:
        font_size = max(5.0, visual_fs)
    else:
        if 0.5 <= (raw_fs / avg_line_height) <= 1.3:
            font_size = round(raw_fs, 1)
        else:
            font_size = max(5.0, visual_fs)

    # 3. Detección automática de tipografía, negrita y cursiva
    flags = s0.get("flags", 0)
    if is_ocr:
        # En OCR, GlyphLessFont tiene flags artificiales (12), por lo que por defecto es Sans-Serif (Helvetica)
        family = "helv"
    else:
        if any(k in raw_fn for k in ("courier", "mono", "consolas", "typewriter", "code")) or (flags & 8):
            family = "cour"
        elif any(k in raw_fn for k in ("times", "serif", "roman", "georgia", "cambria", "garamond", "minion")) or (flags & 4):
            family = "tiro"
        else:
            family = "helv"

    is_bold = bool(flags & 16) or any(
        k in raw_fn for k in ("bold", "black", "heavy", "bld", "medium", "semibold", "w7", "w8", "w9")
    )
    if not is_bold and is_ocr and stroke_density >= 0.28:
        is_bold = True

    is_italic = bool(flags & 2) or any(
        k in raw_fn for k in ("italic", "oblique", "it", "slanted", "kursiv")
    )

    if family == "tiro":
        font_code = "tibi" if (is_bold and is_italic) else ("tibo" if is_bold else ("tiit" if is_italic else "tiro"))
    elif family == "cour":
        font_code = "cobi" if (is_bold and is_italic) else ("cobo" if is_bold else ("coit" if is_italic else "cour"))
    else:
        font_code = "hebi" if (is_bold and is_italic) else ("hebo" if is_bold else ("heit" if is_italic else "helv"))

    # 4. Detección automática de alineación
    detected_align = fitz.TEXT_ALIGN_LEFT
    if len(lines_map) >= 1:
        center_diffs = []
        for line in lines_map:
            lx0 = min(s["bbox"][0] for s in line)
            lx1 = max(s["bbox"][2] for s in line)
            lw = lx1 - lx0
            center_diffs.append(abs((bbox.x0 + bbox.width / 2.0) - (lx0 + lw / 2.0)))
        if len(center_diffs) > 1 and max(center_diffs) <= 4.0:
            detected_align = fitz.TEXT_ALIGN_CENTER
        elif len(center_diffs) == 1 and center_diffs[0] <= 3.0 and bbox.width > 30.0:
            detected_align = fitz.TEXT_ALIGN_CENTER

    card_border = detect_card_border(page, bbox)

    return {
        "bbox": bbox,
        "text": full_text,
        "fontsize": round(font_size, 1),
        "fontname": font_code,
        "color": font_color,
        "fill_color": sampled_bg_col,
        "align": detected_align,
        "card_border": card_border,
    }


def detect_card_border(page: fitz.Page, bbox: fitz.Rect) -> fitz.Rect | None:
    """Detecta si el texto está contenido dentro de un recuadro o tarjeta (vectorial o escaneado)."""
    # 1. Búsqueda en trazados vectoriales (PDFs nativos y diagramas)
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.width >= 15.0 and r.height >= 12.0:
            exp = fitz.Rect(r.x0 - 5.0, r.y0 - 5.0, r.x1 + 5.0, r.y1 + 5.0)
            if exp.contains(bbox.tl) and exp.contains(bbox.br):
                return r

    # 2. Análisis de píxeles para PDFs escaneados o procesados con OCR
    try:
        margin = 10.0
        search_rect = fitz.Rect(
            bbox.x0 - margin, bbox.y0 - margin, bbox.x1 + margin, bbox.y1 + margin
        ).intersect(page.rect)
        scale = 150.0 / 72.0
        pix = page.get_pixmap(clip=search_rect, dpi=150)
        if pix.width < 10 or pix.height < 10:
            return None

        tb_x0 = int((bbox.x0 - search_rect.x0) * scale)
        tb_y0 = int((bbox.y0 - search_rect.y0) * scale)
        tb_x1 = int((bbox.x1 - search_rect.x0) * scale)
        tb_y1 = int((bbox.y1 - search_rect.y0) * scale)

        top_y, bot_y, left_x, right_x = None, None, None, None
        for y in range(0, min(pix.height, tb_y0 + 8)):
            cnt = sum(
                1 for x in range(pix.width)
                if 0.299 * pix.pixel(x, y)[0] + 0.587 * pix.pixel(x, y)[1] + 0.114 * pix.pixel(x, y)[2] < 140
            )
            if cnt >= pix.width * 0.40:
                top_y = y
                break

        for y in range(pix.height - 1, max(0, tb_y1 - 10), -1):
            cnt = sum(
                1 for x in range(pix.width)
                if 0.299 * pix.pixel(x, y)[0] + 0.587 * pix.pixel(x, y)[1] + 0.114 * pix.pixel(x, y)[2] < 140
            )
            if cnt >= pix.width * 0.40:
                bot_y = y
                break

        for x in range(0, min(pix.width, tb_x0 + 8)):
            cnt = sum(
                1 for y in range(pix.height)
                if 0.299 * pix.pixel(x, y)[0] + 0.587 * pix.pixel(x, y)[1] + 0.114 * pix.pixel(x, y)[2] < 140
            )
            if cnt >= pix.height * 0.40:
                left_x = x
                break

        for x in range(pix.width - 1, max(0, tb_x1 - 10), -1):
            cnt = sum(
                1 for y in range(pix.height)
                if 0.299 * pix.pixel(x, y)[0] + 0.587 * pix.pixel(x, y)[1] + 0.114 * pix.pixel(x, y)[2] < 140
            )
            if cnt >= pix.height * 0.40:
                right_x = x
                break

        if top_y is not None and bot_y is not None and left_x is not None and right_x is not None:
            detected_card = fitz.Rect(
                search_rect.x0 + left_x / scale,
                search_rect.y0 + top_y / scale,
                search_rect.x0 + right_x / scale,
                search_rect.y0 + bot_y / scale,
            )
            return detected_card
    except Exception:
        pass

    return None


def replace_text_block(
    doc: fitz.Document,
    page_idx: int,
    bbox: fitz.Rect,
    new_text: str,
    fontsize: float = 12.0,
    fontname: str = "helv",
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    fill_color: tuple[float, float, float] = (1.0, 1.0, 1.0),
    autofit: bool = True,
    align: int = fitz.TEXT_ALIGN_LEFT,
    card_border: fitz.Rect | None = None,
) -> None:
    """Borra limpiamente el bloque existente preservando íntegramente el recuadro y formato exterior."""
    page = doc[page_idx]

    if card_border is None:
        card_border = detect_card_border(page, bbox)

    if card_border is not None:
        # La redacción se realiza ESTRICTAMENTE en el interior de la tarjeta sin tocar ni borrar el contorno
        redact_rect = fitz.Rect(
            card_border.x0 + 1.2,
            card_border.y0 + 1.2,
            card_border.x1 - 1.2,
            card_border.y1 - 1.2,
        )
        target_rect = fitz.Rect(
            card_border.x0 + 2.5,
            card_border.y0 + 2.0,
            card_border.x1 - 2.5,
            card_border.y1 - 2.0,
        )
    else:
        # Texto libre sin recuadro: acotar la redacción al espacio exacto del texto
        redact_rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        needed_w = max(
            (fitz.get_text_length(line, fontname=fontname, fontsize=fontsize) for line in new_text.splitlines()),
            default=0.0
        )
        actual_w = max(bbox.width, needed_w + 4.0)
        actual_w = min(actual_w, page.rect.width - bbox.x0 - 8)
        target_rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x0 + actual_w, bbox.y1 + 2.0)

    # Redactar texto evitando en todo momento eliminar trazados vectoriales o líneas
    page.add_redact_annot(redact_rect, fill=fill_color)
    page.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    new_text = new_text.strip()
    if not new_text:
        # Si se vació y tenía recuadro, asegurar que el recuadro se mantenga nítido y visible
        if card_border is not None:
            shape = page.new_shape()
            shape.draw_rect(card_border)
            shape.finish(color=(0.12, 0.12, 0.12), width=0.75)
            shape.commit()
        return

    # Inserción de texto con autofit acotado dentro del recuadro
    if autofit:
        curr_fs = fontsize
        if curr_fs > 12.0 and target_rect.height < 45.0:
            curr_fs = min(curr_fs, 11.0)
        while curr_fs >= 4.5:
            rc = page.insert_textbox(
                target_rect,
                new_text,
                fontsize=curr_fs,
                fontname=fontname,
                color=color,
                align=align,
            )
            if rc >= 0:
                break
            page.add_redact_annot(redact_rect, fill=fill_color)
            page.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            curr_fs -= 0.5
    else:
        page.insert_textbox(
            target_rect,
            new_text,
            fontsize=fontsize,
            fontname=fontname,
            color=color,
            align=align,
        )

    # Si había una tarjeta / recuadro, redibujar el contorno para garantizar máxima nitidez y que nunca se pierda
    if card_border is not None:
        shape = page.new_shape()
        shape.draw_rect(card_border)
        shape.finish(color=(0.12, 0.12, 0.12), width=0.75)
        shape.commit()


def add_text_box(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    text: str,
    fontsize: float = 12.0,
    fontname: str = "helv",
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    align: int = fitz.TEXT_ALIGN_LEFT,
) -> None:
    """Inserta un nuevo cuadro de texto en la posición especificada."""
    page = doc[page_idx]
    page.insert_textbox(rect, text, fontsize=fontsize, fontname=fontname, color=color, align=align)
