"""Operaciones de edición de contenido (fase 4): texto, imágenes, redacción/censura y enlaces."""
from __future__ import annotations

import html
import os
import re
from html.parser import HTMLParser
from typing import Sequence

import pymupdf as fitz
from .viewer import render_bounded_pixmap
from .pdf_objects import (
    ArrayObject, IndirectObject, get_text_representations,
    get_value, iter_acroform_field_xrefs, parse_object, set_pdf_key_null,
    terminal_field_owner, terminal_field_nodes,
    appearance_streams, reachable_xrefs,
)
from .appearances import AppearanceInspector

MAX_SAMPLE_PIXELS = 65_536


def _page_bounds(page: fitz.Page) -> fitz.Rect:
    """Límites en el mismo espacio no rotado que texto, widgets y dibujos."""
    return (page.rect * page.derotation_matrix).normalize()


class _RichText(HTMLParser):
    """Inline concatena; límites de bloque y br separan palabras/párrafos."""
    _BLOCKS = {"p", "div", "br", "li", "tr", "td", "th", "section", "body"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def _text_matches_phrase(raw_text: str, phrase_low: str) -> bool:
    """Comprueba coincidencias en texto plano y en XHTML/XML con entidades o fragmentación entre nodos (V02)."""
    if not raw_text:
        return False
    low = raw_text.casefold()
    if phrase_low in low:
        return True
    unesc = html.unescape(raw_text).casefold()
    if phrase_low in unesc:
        return True
    no_tags = html.unescape(re.sub(r"<[^>]*>", "", raw_text)).casefold()
    if phrase_low in no_tags:
        return True
    spaced_tags = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", raw_text))).strip().casefold()
    normalized_phrase = " ".join(phrase_low.split())
    parser = _RichText()
    parser.feed(raw_text)
    parser.close()
    semantic_text = " ".join("".join(parser.parts).split()).casefold()
    return normalized_phrase in spaced_tags or normalized_phrase in semantic_text


def _safe_page_widgets(page: fitz.Page) -> list[fitz.Widget]:
    """Itera los widgets de `page` aislando errores individuales de `load_widget`."""
    widgets: list[fitz.Widget] = []
    try:
        annot_entries = list(page.annot_xrefs() or [])
    except Exception:
        annot_entries = []
    if annot_entries:
        for item in annot_entries:
            axref = item[0]
            atype = item[1] if len(item) > 1 else None
            if atype not in (None, fitz.PDF_ANNOT_WIDGET):
                continue
            try:
                w = page.load_widget(axref)
                if w is not None:
                    widgets.append(w)
            except Exception:
                continue
        return widgets
    try:
        return list(page.widgets())
    except Exception:
        return []


def _field_family_xrefs(doc, xref: int) -> list[int]:
    return terminal_field_nodes(doc, xref)


def _field_has_phrase(doc, xref: int, phrase: str, inspector=None) -> bool:
    phrase_low = phrase.casefold()
    for node in _field_family_xrefs(doc, xref):
        for key in ("V", "DV", "RV", "DS", "TU", "TM", "Opt"):
            for text_rep in get_text_representations(doc, node, key):
                if _text_matches_phrase(text_rep, phrase_low):
                    return True
        if inspector is not None and any(_text_matches_phrase(t, phrase_low) for t in inspector.texts(node)):
            return True
    return False


def _field_widget_pages(doc: fitz.Document) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for pno, page in enumerate(doc):
        for entry in page.annot_xrefs():
            if entry[1] != fitz.PDF_ANNOT_WIDGET:
                continue
            owner = terminal_field_owner(doc, entry[0])
            if owner is None:
                raise ValueError("No se pudo inspeccionar un campo de formulario para censurarlo.")
            result.setdefault(owner, set()).add(pno)
    return result


def _require_complete_field_scope(roots: set[int], selected: set[int], locations: dict[int, set[int]]) -> None:
    if any(locations.get(root, set()) - selected for root in roots):
        raise ValueError(
            "Un campo afectado se comparte con páginas fuera del rango elegido. "
            "Incluya todas las páginas de ese campo para censurarlo sin modificar páginas excluidas."
        )


def _annot_has_phrase(doc, annot: fitz.Annot, phrase_low: str, inspector=None) -> bool:
    info = annot.info or {}
    for k in ("content", "title", "subject"):
        if _text_matches_phrase(str(info.get(k, "") or ""), phrase_low):
            return True
    xref = getattr(annot, "xref", 0) or 0
    if xref > 0:
        target_xrefs = [xref]
        pk, pv = doc.xref_get_key(xref, "Popup")
        if pk == "xref":
            try:
                target_xrefs.append(int(pv.split()[0]))
            except Exception:
                pass
        for tx in target_xrefs:
            for key in ("RC", "Contents", "T", "Subj", "DS"):
                for text_rep in get_text_representations(doc, tx, key):
                    if _text_matches_phrase(text_rep, phrase_low):
                        return True
            if inspector is not None and any(_text_matches_phrase(t, phrase_low) for t in inspector.texts(tx)):
                return True
    return False


def _xfa_has_phrase(doc: fitz.Document, phrase_low: str) -> bool:
    cat = doc.pdf_catalog()
    for text_rep in get_text_representations(doc, cat, "AcroForm/XFA"):
        if _text_matches_phrase(text_rep, phrase_low):
            return True
    return False


def _remove_xfa_completely(doc: fitz.Document) -> None:
    """Limpia streams/objetos indirectos de XFA y anula AcroForm/XFA (V02)."""
    cat = doc.pdf_catalog()
    try:
        kind, raw = doc.xref_get_key(cat, "AcroForm/XFA")
        if kind != "null":
            obj = parse_object(raw)
            items = list(obj) if isinstance(obj, ArrayObject) else [obj]
            for it in items:
                if isinstance(it, IndirectObject) and it.idnum > 0:
                    if doc.xref_is_stream(it.idnum):
                        doc.update_stream(it.idnum, b"", compress=False)
                    doc.update_object(it.idnum, "<< >>")
    except Exception:
        pass
    set_pdf_key_null(doc, cat, "AcroForm/XFA")


def _wipe_indirect_key_value(doc: fitz.Document, xref: int, key: str, protected=frozenset()) -> None:
    """Limpia tanto la clave en `xref` como cualquier stream u objeto indirecto referenciado por ella."""
    try:
        kind, val = doc.xref_get_key(xref, key)
    except Exception:
        return
    if kind == "xref":
        try:
            ref_id = int(val.split()[0])
            if ref_id > 0 and ref_id not in protected:
                if doc.xref_is_stream(ref_id):
                    doc.update_stream(ref_id, b"", compress=False)
                doc.update_object(ref_id, "<< >>")
        except Exception:
            pass
    try:
        doc.xref_set_key(xref, key, "null")
    except Exception:
        pass


def _wipe_appearance_streams(doc, nodes, protected):
    for node in nodes:
        for stream in appearance_streams(doc, node):
            if stream not in protected:
                doc.update_stream(stream, b"", compress=False)
                doc.update_object(stream, "<< >>")


def _preserved_objects(doc, roots, annot_xrefs):
    excluded = {node for root in roots for node in _field_family_xrefs(doc, root)}
    for xref in annot_xrefs:
        excluded.add(xref)
        kind, raw = doc.xref_get_key(xref, "Popup")
        if kind == "xref":
            excluded.add(int(raw.split()[0]))
    return reachable_xrefs(doc, excluded=excluded)


def _wipe_field_nodes(doc: fitz.Document, nodes: list[int], protected: set[int]) -> None:
    _wipe_appearance_streams(doc, nodes, protected)
    for node in nodes:
        for key in ("V", "DV", "RV", "DS", "TU", "TM", "Opt", "I", "T"):
            _wipe_indirect_key_value(doc, node, key, protected)
        for key in ("AP", "AS"):
            _wipe_indirect_key_value(doc, node, key, protected)


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
    """Inserta un cuadro de texto en la página especificada."""
    page = doc[page_idx]
    # Si el rect es muy pequeño o un punto, crear un área por defecto hacia abajo a la derecha
    if rect.width < 10 or rect.height < 10:
        p_rect = _page_bounds(page)
        w = max(150.0, min(300.0, p_rect.x1 - rect.x0 - 20))
        h = max(30.0, fontsize * 2.5)
        rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + w, rect.y0 + h)

    # Verificar primero en un shape temporal si cabe en rect o en expanded_rect (H07)
    target_rect = rect
    test_shape = page.new_shape()
    rc = test_shape.insert_textbox(
        target_rect,
        text,
        fontsize=fontsize,
        fontname=fontname,
        color=color,
        align=align,
    )
    if rc < 0:
        expanded_rect = fitz.Rect(rect.x0, rect.y0, max(rect.x1, _page_bounds(page).width - 20), _page_bounds(page).height - 20)
        test_shape2 = page.new_shape()
        rc = test_shape2.insert_textbox(
            expanded_rect,
            text,
            fontsize=fontsize,
            fontname=fontname,
            color=color,
            align=align,
        )
        if rc < 0:
            raise ValueError("El texto excede el espacio disponible en la página y no pudo insertarse.")
        target_rect = expanded_rect

    final_rc = page.insert_textbox(
        target_rect,
        text,
        fontsize=fontsize,
        fontname=fontname,
        color=color,
        align=align,
    )
    if final_rc < 0:
        raise ValueError("El texto excede el espacio disponible en la página y no pudo insertarse.")


def _delete_widget_completely(doc: fitz.Document, page: fitz.Page, w: fitz.Widget, protected: set[int]) -> None:
    """Limpia valores, representaciones enriquecidas (/RV), padres y apariencias del widget (H45, V02)."""
    xref = getattr(w, "xref", 0) or 0
    nodes = _field_family_xrefs(doc, xref) if xref > 0 else []
    try:
        page.delete_widget(w)
    except Exception:
        pass
    _wipe_field_nodes(doc, nodes, protected)


def _delete_annot_completely(doc: fitz.Document, page: fitz.Page, a: fitz.Annot, protected: set[int]) -> None:
    """Limpia contenido plano y enriquecido (/RC), popup y apariencias antes de borrar la anotación (V02)."""
    xref = getattr(a, "xref", 0) or 0
    target_xrefs: list[int] = []
    if xref > 0:
        target_xrefs.append(xref)
        try:
            pk, pv = doc.xref_get_key(xref, "Popup")
            if pk == "xref":
                target_xrefs.append(int(pv.split()[0]))
        except Exception:
            pass
    try:
        page.delete_annot(a)
    except Exception:
        pass
    _wipe_appearance_streams(doc, target_xrefs, protected)
    for tx in target_xrefs:
        for key in ("RC", "Contents", "T", "Subj", "DS", "AP", "Popup"):
            _wipe_indirect_key_value(doc, tx, key, protected)


def apply_redaction(
    doc: fitz.Document,
    page_idx: int,
    rect: fitz.Rect,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    text: str = "",
    *,
    remove_xfa: bool = False,
) -> None:
    """Censura / redacta físicamente el área rectangular especificada."""
    from .security import UnsupportedActiveContentError, has_xfa
    page = doc[page_idx]
    widgets_to_delete = [w for w in list(page.widgets()) if w.rect.intersects(rect)]
    roots = {terminal_field_owner(doc, w.xref) for w in widgets_to_delete}
    _require_complete_field_scope(roots, {page_idx}, _field_widget_pages(doc))
    annots_to_delete = [a for a in page.annots() if a.rect.intersects(rect)]
    protected = _preserved_objects(doc, roots, [a.xref for a in annots_to_delete])
    if has_xfa(doc):
        if not remove_xfa:
            raise UnsupportedActiveContentError(
                "El PDF contiene XFA. Debe autorizar la eliminación de XFA para censurar el documento."
            )
        _remove_xfa_completely(doc)
    for w in widgets_to_delete:
        _delete_widget_completely(doc, page, w, protected)
    for a in annots_to_delete:
        _delete_annot_completely(doc, page, a, protected)
    page.add_redact_annot(rect, text=text, fill=fill_color)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)


def redact_search_phrase(
    doc: fitz.Document,
    phrase: str,
    pages: Sequence[int] | None = None,
    fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    remove_xfa: bool = False,
) -> int:
    """Busca una frase y redacta físicamente todas sus ocurrencias en texto, formularios y anotaciones (H45, V02)."""
    from .security import UnsupportedActiveContentError, has_xfa
    phrase_clean = phrase.strip()
    if not phrase_clean:
        return 0
    phrase_low = phrase_clean.casefold()
    target_pages = sorted(set(pages if pages is not None else range(doc.page_count)))
    if not target_pages or any(p < 0 or p >= doc.page_count for p in target_pages):
        raise ValueError("La selección de páginas no es válida.")
    selected = set(target_pages)
    field_locations = _field_widget_pages(doc)
    owners = set(field_locations)
    if len(selected) == doc.page_count:
        owners.update(owner for x in iter_acroform_field_xrefs(doc)
                      if (owner := terminal_field_owner(doc, x)) is not None)
    else:
        owners = {root for root in owners if field_locations[root] & selected}
    matches_by_page = {pno: list(doc[pno].search_for(phrase_clean)) for pno in target_pages}
    matched_annotations = set()
    # Preflight antes de cualquier mutación, también para coincidencias que cruzan un widget.
    with AppearanceInspector(doc) as inspector:
        global_matched_roots = {root for root in owners if _field_has_phrase(doc, root, phrase_low, inspector)}
        for pno in target_pages:
            page = doc[pno]
            for w in _safe_page_widgets(page):
                if (any(w.rect.intersects(r) for r in matches_by_page[pno])
                        or _field_has_phrase(doc, w.xref, phrase_low, inspector)
                        or _text_matches_phrase(str(w.field_value or ""), phrase_low)
                        or _text_matches_phrase(str(getattr(w, "field_label", "") or ""), phrase_low)):
                    global_matched_roots.add(terminal_field_owner(doc, w.xref))
            for a in page.annots():
                if (any(a.rect.intersects(r) for r in matches_by_page[pno])
                        or _annot_has_phrase(doc, a, phrase_low, inspector)):
                    matched_annotations.add(a.xref)
    _require_complete_field_scope(global_matched_roots, selected, field_locations)
    protected = _preserved_objects(doc, global_matched_roots, matched_annotations)
    if has_xfa(doc):
        if remove_xfa:
            _remove_xfa_completely(doc)
        elif _xfa_has_phrase(doc, phrase_low):
            raise UnsupportedActiveContentError(
                "El PDF contiene datos XFA alternativos con el texto buscado. "
                "Autorice la eliminación de XFA para evitar conservar el secreto."
            )
    total_matches = 0

    for pno in target_pages:
        page = doc[pno]
        matches = matches_by_page[pno]
        redact_rects: list[fitz.Rect] = [
            fitz.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5) for r in matches
        ]
        page_hits = len(matches)

        # Resolver primero todos los widgets y sus familias lógicas antes de mutar el árbol AcroForm
        page_widgets = _safe_page_widgets(page)
        matched_roots: set[int] = set(global_matched_roots)
        widget_decisions: list[tuple[fitz.Widget, fitz.Rect, bool, int]] = []
        handled_roots_on_page: set[int] = set()
        for w in page_widgets:
            w_rect = fitz.Rect(w.rect)
            root_xref = terminal_field_owner(doc, w.xref)
            intersects_match = any(w_rect.intersects(r) for r in matches)
            has_secret_val = (
                _text_matches_phrase(str(w.field_value or ""), phrase_low)
                or _text_matches_phrase(str(getattr(w, "field_label", "") or ""), phrase_low)
                or _field_has_phrase(doc, w.xref, phrase_low)
            )
            if intersects_match or has_secret_val:
                matched_roots.add(root_xref)
            widget_decisions.append((w, w_rect, intersects_match, root_xref))

        for w, w_rect, intersects_match, root_xref in widget_decisions:
            if root_xref in matched_roots:
                handled_roots_on_page.add(root_xref)
                if not intersects_match:
                    page_hits += 1
                redact_rects.append(w_rect)
                _delete_widget_completely(doc, page, w, protected)

        # Si hay widgets en Annots cuya carga como fitz.Widget falló pero pertenecen a una familia afectada
        try:
            raw_annot_xrefs = [it[0] for it in (page.annot_xrefs() or [])]
        except Exception:
            raw_annot_xrefs = []
        for axref in raw_annot_xrefs:
            root_xref = terminal_field_owner(doc, axref)
            if root_xref in matched_roots and root_xref not in handled_roots_on_page:
                handled_roots_on_page.add(root_xref)
                page_hits += 1
                rect_obj = get_value(doc, axref, "Rect")
                if isinstance(rect_obj, ArrayObject) and len(rect_obj) == 4:
                    try:
                        redact_rects.append(fitz.Rect(*[float(x) for x in rect_obj]))
                    except Exception:
                        pass
                _wipe_field_nodes(doc, _field_family_xrefs(doc, root_xref), protected)

        try:
            page_annots = list(page.annots())
        except Exception:
            page_annots = []
        annot_decisions: list[tuple[fitz.Annot, fitz.Rect, bool, bool]] = []
        for a in page_annots:
            a_rect = fitz.Rect(a.rect)
            intersects_match = any(a_rect.intersects(r) for r in matches)
            has_secret_annot = a.xref in matched_annotations
            annot_decisions.append((a, a_rect, intersects_match, has_secret_annot))

        for a, a_rect, intersects_match, has_secret_annot in annot_decisions:
            if intersects_match or has_secret_annot:
                if not intersects_match:
                    page_hits += 1
                redact_rects.append(a_rect)
                _delete_annot_completely(doc, page, a, protected)

        if redact_rects:
            for r in redact_rects:
                page.add_redact_annot(r, fill=fill_color)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

            # Segunda pasada por si algún glifo o apariencia remanente quedó parcialmente fuera del bbox
            residual = list(page.search_for(phrase_clean))
            if residual:
                for r in residual:
                    page.add_redact_annot(
                        fitz.Rect(r.x0 - 1.5, r.y0 - 1.5, r.x1 + 1.5, r.y1 + 1.5),
                        fill=fill_color,
                    )
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

            total_matches += page_hits

    if global_matched_roots:
        for root_xref in global_matched_roots:
            nodes = _field_family_xrefs(doc, root_xref)
            _wipe_field_nodes(doc, nodes, protected)
        if total_matches == 0:
            total_matches = len(global_matched_roots)
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
    """Extrae todas las imágenes incrustadas de las páginas indicadas sin sobrescribir archivos existentes (H28)."""
    from .attachments import unique_path

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
            out_path = unique_path(os.path.join(out_dir, out_name))
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
        pix = render_bounded_pixmap(page, clip=bbox * page.rotation_matrix,
                                   dpi=150, max_pixels=MAX_SAMPLE_PIXELS)
        if pix.width < 2 or pix.height < 2:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.0

        from collections import Counter
        data = pix.samples
        counts = Counter(zip(data[0::pix.n], data[1::pix.n], data[2::pix.n]))

        # El color más frecuente es el fondo
        bg_cand = counts.most_common(1)[0][0]
        bg_r, bg_g, bg_b = bg_cand

        # Píxeles de texto: aquellos que difieren sustancialmente del fondo
        def dist_sq(p):
            return (p[0] - bg_r) ** 2 + (p[1] - bg_g) ** 2 + (p[2] - bg_b) ** 2

        text_counts = [(p, n) for p, n in counts.items() if dist_sq(p) > 1600]
        text_count = sum(n for _, n in text_counts)
        density = text_count / (pix.width * pix.height)

        if text_count:
            text_counts.sort(key=lambda item: 0.299 * item[0][0] + 0.587 * item[0][1] + 0.114 * item[0][2])
            core_size = remaining = max(1, text_count // 2)
            sums = [0, 0, 0]
            for color, count in text_counts:
                take = min(remaining, count)
                for channel in range(3):
                    sums[channel] += color[channel] * take
                remaining -= take
                if not remaining:
                    break
            avg_r, avg_g, avg_b = (value / core_size / 255.0 for value in sums)

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
    if selection_rect is not None and selection_rect.width > 15 and selection_rect.height > 6:
        for s in all_spans:
            s_rect = fitz.Rect(s["bbox"])
            v_overlap = max(0.0, min(selection_rect.y1, s_rect.y1) - max(selection_rect.y0, s_rect.y0))
            h_overlap = max(0.0, min(selection_rect.x1, s_rect.x1) - max(selection_rect.x0, s_rect.x0))
            sh = max(1.0, s_rect.height)
            sw = max(1.0, s_rect.width)
            # Solo incluir spans que estén sustancialmente dentro de la selección vertical y horizontalmente
            if v_overlap >= 0.5 * sh and h_overlap >= 0.25 * sw:
                cluster.append(s)

    # Caso 2: Clic puntual o selección de fila: aislar exactamente la fila/renglón horizontal
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

        tb = fitz.Rect(target_span["bbox"])
        th = max(1.0, tb.height)

        def _span_style_key(sp: dict) -> tuple[str, float, int]:
            fn = sp.get("font", "").lower()
            fl = sp.get("flags", 0)
            sz = round(float(sp.get("size", 10.0)), 1)
            col = int(sp.get("color", 0)) if isinstance(sp.get("color"), int) else 0
            return (fn, sz, fl, col)

        target_style = _span_style_key(target_span)

        # Buscar los spans de la misma fila horizontal que compartan el mismo estilo (H30)
        row_spans = []
        for s in all_spans:
            sb = fitz.Rect(s["bbox"])
            sh = max(1.0, sb.height)
            v_overlap = max(0.0, min(tb.y1, sb.y1) - max(tb.y0, sb.y0))
            if v_overlap >= 0.45 * min(th, sh):
                row_spans.append(s)

        row_spans.sort(key=lambda s: s["bbox"][0])
        target_idx = -1
        for idx, s in enumerate(row_spans):
            if s is target_span or fitz.Rect(s["bbox"]) == tb:
                target_idx = idx
                break

        if target_idx >= 0:
            left_spans = []
            cur_x0 = row_spans[target_idx]["bbox"][0]
            for i in range(target_idx - 1, -1, -1):
                s = row_spans[i]
                if cur_x0 - s["bbox"][2] <= 12.0 and _span_style_key(s) == target_style:
                    left_spans.append(s)
                    cur_x0 = s["bbox"][0]
                else:
                    break
            left_spans.reverse()

            right_spans = []
            cur_x1 = row_spans[target_idx]["bbox"][2]
            for i in range(target_idx + 1, len(row_spans)):
                s = row_spans[i]
                if s["bbox"][0] - cur_x1 <= 12.0 and _span_style_key(s) == target_style:
                    right_spans.append(s)
                    cur_x1 = s["bbox"][2]
                else:
                    break

            cluster = left_spans + [row_spans[target_idx]] + right_spans
        else:
            cluster = [target_span]

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

    # 1. Detección automática del color (PDF nativo vs muestreo visual en OCR) (H30)
    sampled_text_col, sampled_bg_col, stroke_density = sample_visual_colors(page, bbox)
    raw_fn = s0.get("font", "").lower()
    is_ocr = ("glyphless" in raw_fn) or ("tess" in raw_fn)
    raw_col = s0.get("color", None)
    if not is_ocr and isinstance(raw_col, int):
        r = ((raw_col >> 16) & 0xFF) / 255.0
        g = ((raw_col >> 8) & 0xFF) / 255.0
        b_c = (raw_col & 0xFF) / 255.0
        font_color = (round(r, 2), round(g, 2), round(b_c, 2))
    else:
        font_color = sampled_text_col

    # 2. Detección automática del tamaño de fuente
    raw_fs = s0.get("size", 10.0)
    is_corrupt_size = (raw_fs < 3.0) or (raw_fs > 120.0)

    if is_ocr or is_corrupt_size:
        font_size = max(5.0, visual_fs)
    else:
        # En PDFs nativos, raw_fs es el tamaño de fuente exacto y real del documento
        font_size = round(raw_fs, 1)

    # 3. Detección automática de tipografía, negrita y cursiva
    def _resolve_span_font_code(sp: dict) -> tuple[str, tuple[float, float, float], float]:
        sp_fn = sp.get("font", "").lower()
        sp_flags = sp.get("flags", 0)
        sp_ocr = ("glyphless" in sp_fn) or ("tess" in sp_fn)
        if sp_ocr:
            fam = "helv"
        elif any(k in sp_fn for k in ("courier", "mono", "consolas", "typewriter", "code")) or (sp_flags & 8):
            fam = "cour"
        elif any(k in sp_fn for k in ("times", "serif", "roman", "georgia", "cambria", "garamond", "minion")) or (sp_flags & 4):
            fam = "tiro"
        else:
            fam = "helv"
        sp_bold = bool(sp_flags & 16) or any(
            k in sp_fn for k in ("bold", "black", "heavy", "bld", "medium", "semibold", "w7", "w8", "w9")
        )
        if not sp_bold and sp_ocr and stroke_density >= 0.28:
            sp_bold = True
        sp_it = bool(sp_flags & 2) or any(
            k in sp_fn for k in ("italic", "oblique", "it", "slanted", "kursiv")
        )
        if fam == "tiro":
            fcode = "tibi" if (sp_bold and sp_it) else ("tibo" if sp_bold else ("tiit" if sp_it else "tiro"))
        elif fam == "cour":
            fcode = "cobi" if (sp_bold and sp_it) else ("cobo" if sp_bold else ("coit" if sp_it else "cour"))
        else:
            fcode = "hebi" if (sp_bold and sp_it) else ("hebo" if sp_bold else ("heit" if sp_it else "helv"))
        sp_col_raw = sp.get("color", None)
        if not sp_ocr and isinstance(sp_col_raw, int):
            sp_col = (
                round(((sp_col_raw >> 16) & 0xFF) / 255.0, 2),
                round(((sp_col_raw >> 8) & 0xFF) / 255.0, 2),
                round((sp_col_raw & 0xFF) / 255.0, 2),
            )
        else:
            sp_col = sampled_text_col
        sp_fs = float(sp.get("size", font_size))
        if sp_ocr or sp_fs < 3.0 or sp_fs > 120.0:
            sp_fs = font_size
        return fcode, sp_col, round(sp_fs, 1)

    font_code, font_color, font_size = _resolve_span_font_code(s0)

    runs = []
    style_set = set()
    for sp in cluster:
        fc, col, fs = _resolve_span_font_code(sp)
        style_set.add((fc, col, fs))
        runs.append({
            "text": sp.get("text", "").strip(),
            "bbox": fitz.Rect(sp["bbox"]),
            "fontname": fc,
            "color": col,
            "fontsize": fs,
        })
    has_mixed_styles = len(style_set) > 1

    # 4. Detección automática de alineación
    detected_align = fitz.TEXT_ALIGN_LEFT
    if len(lines_map) > 1:
        center_diffs = []
        left_diffs = []
        for line in lines_map:
            lx0 = min(s["bbox"][0] for s in line)
            lx1 = max(s["bbox"][2] for s in line)
            lw = lx1 - lx0
            center_diffs.append(abs((bbox.x0 + bbox.width / 2.0) - (lx0 + lw / 2.0)))
            left_diffs.append(abs(lx0 - bbox.x0))
        if max(center_diffs) <= 4.0 and max(center_diffs) < max(left_diffs):
            detected_align = fitz.TEXT_ALIGN_CENTER
    elif len(lines_map) == 1:
        # Para un único renglón, sólo es centrado si está alineado al centro de la página
        page_center = page.rect.width / 2.0
        line_center = bbox.x0 + bbox.width / 2.0
        if abs(line_center - page_center) <= 15.0 and bbox.width < page.rect.width * 0.7:
            detected_align = fitz.TEXT_ALIGN_CENTER
        else:
            detected_align = fitz.TEXT_ALIGN_LEFT

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
        "runs": runs,
        "has_mixed_styles": has_mixed_styles,
    }


def detect_card_border(page: fitz.Page, bbox: fitz.Rect) -> fitz.Rect | None:
    """Detecta si el texto está contenido dentro de un recuadro o tarjeta pequeña (vectorial o escaneado).
    Descarta fondos de página completos, márgenes o contenedores masivos para evitar borrar contenido adyacente."""
    # 1. Búsqueda en trazados vectoriales (PDFs nativos y diagramas)
    candidates = []
    page_area = _page_bounds(page).get_area()
    bbox_area = bbox.get_area()

    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.width < 15.0 or r.height < 12.0:
            continue
        # Descartar estrictamente dibujos de fondo de página, márgenes o lienzos grandes
        if r.width >= _page_bounds(page).width * 0.70 or r.height >= _page_bounds(page).height * 0.50:
            continue
        if r.get_area() >= page_area * 0.25:
            continue
        # Debe envolver estrechamente el bloque de texto (no una sección masiva o columna)
        if r.width > bbox.width + 50.0 or r.height > bbox.height + 50.0:
            continue
        if r.get_area() > max(bbox_area * 2.5, bbox_area + 2500):
            continue
        exp = fitz.Rect(r.x0 - 4.0, r.y0 - 4.0, r.x1 + 4.0, r.y1 + 4.0)
        if exp.contains(bbox.tl) and exp.contains(bbox.br):
            candidates.append(r)

    if candidates:
        return min(candidates, key=lambda c: c.get_area())

    if page.rotation:
        return None

    # 2. Análisis de píxeles para PDFs escaneados o procesados con OCR
    try:
        margin = 10.0
        search_rect = fitz.Rect(
            bbox.x0 - margin, bbox.y0 - margin, bbox.x1 + margin, bbox.y1 + margin
        ).intersect(page.rect)
        pix = render_bounded_pixmap(page, clip=search_rect, dpi=150, max_pixels=MAX_SAMPLE_PIXELS)
        if pix.width < 10 or pix.height < 10:
            return None

        scale_x, scale_y = pix.width / search_rect.width, pix.height / search_rect.height
        tb_x0 = int((bbox.x0 - search_rect.x0) * scale_x)
        tb_y0 = int((bbox.y0 - search_rect.y0) * scale_y)
        tb_x1 = int((bbox.x1 - search_rect.x0) * scale_x)
        tb_y1 = int((bbox.y1 - search_rect.y0) * scale_y)

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
                search_rect.x0 + left_x / scale_x,
                search_rect.y0 + top_y / scale_y,
                search_rect.x0 + right_x / scale_x,
                search_rect.y0 + bot_y / scale_y,
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
    """Borra limpiamente el bloque de texto existente preservando intacto el resto de la página."""
    page = doc[page_idx]

    # Validación de seguridad: verificar que si se pasa card_border, sea un recuadro pequeño y no el fondo de la página
    if card_border is not None:
        if (
            card_border.width >= _page_bounds(page).width * 0.70
            or card_border.height >= _page_bounds(page).height * 0.50
            or card_border.get_area() >= _page_bounds(page).get_area() * 0.25
            or card_border.get_area() > max(bbox.get_area() * 2.5, bbox.get_area() + 2500)
        ):
            card_border = None

    if card_border is None:
        card_border = detect_card_border(page, bbox)

    if card_border is not None:
        # Texto dentro de una pequeña tarjeta o botón acotado:
        # Redactar el interior sin tocar el contorno exterior
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
        # Texto libre en la página:
        # La redacción debe cubrir ESTRICTAMENTE el área del texto original a reemplazar,
        # con un margen de 1 punto para cubrir astas de letras, SIN tocar texto o imágenes adyacentes.
        redact_rect = fitz.Rect(
            max(0.0, bbox.x0 - 1.0),
            max(0.0, bbox.y0 - 1.0),
            min(_page_bounds(page).width, bbox.x1 + 1.0),
            min(_page_bounds(page).height, bbox.y1 + 1.5),
        )

        lines = new_text.splitlines() or [""]
        needed_w = max(
            (fitz.get_text_length(line, fontname=fontname, fontsize=fontsize) for line in lines),
            default=0.0
        )
        actual_w = max(bbox.width, needed_w + 14.0)
        actual_w = min(actual_w, _page_bounds(page).width - bbox.x0 - 6.0)

        line_h = fontsize * 1.35
        needed_h = max(bbox.height, len(lines) * line_h + 6.0)
        actual_h = min(needed_h, _page_bounds(page).height - bbox.y0 - 6.0)

        target_rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x0 + actual_w, bbox.y0 + actual_h)

    cleaned_text = new_text.strip()
    final_rect = target_rect
    final_fs = fontsize

    # H06: Antes de borrar el texto original, verificar en memoria si el nuevo texto cabe
    if cleaned_text:
        fitted = False
        if autofit:
            curr_fs = fontsize
            while curr_fs >= 4.5:
                tshape = page.new_shape()
                rc = tshape.insert_textbox(
                    target_rect,
                    cleaned_text,
                    fontsize=curr_fs,
                    fontname=fontname,
                    color=color,
                    align=align,
                )
                if rc >= 0:
                    fitted = True
                    final_fs = curr_fs
                    final_rect = target_rect
                    break
                curr_fs -= 0.5
            if not fitted and card_border is None:
                expanded = fitz.Rect(
                    target_rect.x0,
                    target_rect.y0,
                    min(_page_bounds(page).width - 6.0, target_rect.x1 + 30.0),
                    _page_bounds(page).height - 6.0,
                )
                tshape = page.new_shape()
                rc = tshape.insert_textbox(
                    expanded,
                    cleaned_text,
                    fontsize=4.5,
                    fontname=fontname,
                    color=color,
                    align=align,
                )
                if rc >= 0:
                    fitted = True
                    final_fs = 4.5
                    final_rect = expanded
        else:
            tshape = page.new_shape()
            rc = tshape.insert_textbox(
                target_rect,
                cleaned_text,
                fontsize=fontsize,
                fontname=fontname,
                color=color,
                align=align,
            )
            if rc >= 0:
                fitted = True
                final_rect = target_rect
            elif card_border is None:
                expanded = fitz.Rect(
                    target_rect.x0,
                    target_rect.y0,
                    min(_page_bounds(page).width - 6.0, target_rect.x1 + 30.0),
                    _page_bounds(page).height - 6.0,
                )
                tshape = page.new_shape()
                rc = tshape.insert_textbox(
                    expanded,
                    cleaned_text,
                    fontsize=fontsize,
                    fontname=fontname,
                    color=color,
                    align=align,
                )
                if rc >= 0:
                    fitted = True
                    final_rect = expanded

        if not fitted:
            raise ValueError(
                "El nuevo texto excede el espacio disponible en la página y no pudo insertarse sin pérdida de datos."
            )

    # Aplicar las mismas garantías de alcance y recursos que la censura manual.
    widgets = [w for w in page.widgets() if w.rect.intersects(redact_rect)]
    annots = [a for a in page.annots() if a.rect.intersects(redact_rect)]
    roots = {terminal_field_owner(doc, w.xref) for w in widgets}
    _require_complete_field_scope(roots, {page_idx}, _field_widget_pages(doc))
    protected = _preserved_objects(doc, roots, [a.xref for a in annots])
    for w in widgets:
        _delete_widget_completely(doc, page, w, protected)
    for a in annots:
        _delete_annot_completely(doc, page, a, protected)

    # Redactar texto existente (evitando eliminar trazados vectoriales)
    page.add_redact_annot(redact_rect, fill=fill_color)
    page.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    if not cleaned_text:
        if card_border is not None:
            shape = page.new_shape()
            shape.draw_rect(card_border)
            shape.finish(color=(0.12, 0.12, 0.12), width=0.75)
            shape.commit()
        return

    rc = page.insert_textbox(
        final_rect,
        cleaned_text,
        fontsize=final_fs,
        fontname=fontname,
        color=color,
        align=align,
    )
    if rc < 0:
        raise ValueError("No fue posible insertar el texto en el área seleccionada.")

    # Si había una tarjeta / recuadro, redibujar el contorno para garantizar máxima nitidez
    if card_border is not None:
        shape = page.new_shape()
        shape.draw_rect(card_border)
        shape.finish(color=(0.12, 0.12, 0.12), width=0.75)
        shape.commit()

