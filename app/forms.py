"""
Módulo para gestión, rellenado y aplanado de formularios PDF (AcroForms) y protección de firmas.
"""
from __future__ import annotations

from typing import Any
import pymupdf as fitz
from .pdf_objects import array_strings


def has_signature_fields(doc: fitz.Document) -> bool:
    """Indica si el documento contiene al menos un campo de formulario de tipo Firma (/FT /Sig)."""
    try:
        for page in doc:
            for w in page.widgets():
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    return True
    except Exception:
        pass
    return False


def _xref_has_sig_dict(doc: fitz.Document, xref: int) -> bool:
    """Comprueba si el objeto `xref` (o su padre) tiene un diccionario /V con /ByteRange o /Contents."""
    visited: set[int] = set()
    cur = xref
    while cur and cur > 0 and cur not in visited:
        visited.add(cur)
        kind, val = doc.xref_get_key(cur, "V")
        if kind == "dict":
            if "/ByteRange" in val or "/Contents" in val:
                return True
        elif kind == "xref":
            try:
                v_xref = int(val.split()[0])
                v_obj = doc.xref_object(v_xref) or ""
                if "/ByteRange" in v_obj or "/Contents" in v_obj:
                    return True
            except Exception:
                pass
        p_kind, p_val = doc.xref_get_key(cur, "Parent")
        if p_kind == "xref":
            try:
                cur = int(p_val.split()[0])
                continue
            except Exception:
                break
        break
    return False


def document_has_signatures(doc: fitz.Document) -> bool:
    """Verifica si el documento contiene firmas digitales efectivamente aplicadas (N04 / H49).

    Distingue un campo de firma vacío (`/FT /Sig` con `/V null`, que NO está firmado) de un campo
    que realmente posee diccionario de firma (`/V` con `/ByteRange` / `/Contents` o `is_signed=True`).
    """
    try:
        for page in doc:
            for w in page.widgets():
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    if getattr(w, "is_signed", False) or _xref_has_sig_dict(doc, w.xref):
                        return True
    except Exception:
        pass
    return False


def _parse_pdf_array_strings(raw_array: str) -> list[str]:
    """Cadenas PDF completas: literales, escapes octales y hex UTF-16."""
    return array_strings(raw_array)


def _normalize_choices(raw_choices: Any) -> list[str]:
    if not raw_choices:
        return []
    out: list[str] = []
    for c in raw_choices:
        if isinstance(c, (list, tuple)) and len(c) >= 1:
            out.append(str(c[0]))
        else:
            out.append(str(c))
    return out


def _get_xref_v_array(doc: fitz.Document, xref: int) -> list[str] | None:
    visited: set[int] = set()
    cur = xref
    while cur and cur > 0 and cur not in visited:
        visited.add(cur)
        kind, val = doc.xref_get_key(cur, "V")
        if kind == "array":
            return _parse_pdf_array_strings(val)
        p_kind, p_val = doc.xref_get_key(cur, "Parent")
        if p_kind == "xref":
            try:
                cur = int(p_val.split()[0])
                continue
            except Exception:
                break
        break
    return None


def get_form_fields(doc: fitz.Document) -> list[dict[str, Any]]:
    """Obtiene todos los campos de formulario presentes en el PDF con sus valores actuales."""
    fields = []
    multi_flag = getattr(fitz, "PDF_CH_FIELD_IS_MULTI_SELECT", 1 << 21)
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for w in page.widgets():
            ft = w.field_type_string
            val: Any = w.field_value
            raw_choices = getattr(w, "choice_values", None) or []
            choices = _normalize_choices(raw_choices)
            choice_labels = [str(c[1]) if isinstance(c, (list, tuple)) and len(c) > 1 else str(c)
                             for c in raw_choices]

            is_sig = (w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE)
            flags = getattr(w, "field_flags", 0) or 0
            is_read_only = bool(flags & fitz.PDF_FIELD_IS_READ_ONLY)
            is_multi = bool(flags & multi_flag)

            if w.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX:
                ft = "ComboBox"
            elif w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX:
                ft = "ListBox"
                arr_val = _get_xref_v_array(doc, w.xref)
                if arr_val is not None:
                    val = arr_val
                    is_multi = True
                elif is_multi:
                    val = [str(val)] if val else []

            fields.append({
                "page": page_idx,
                "xref": w.xref,
                "name": w.field_name or f"Campo_P{page_idx+1}",
                "label": w.field_label or w.field_name or "",
                "type": "Signature" if is_sig else ft,
                "value": val,
                "rect": w.rect,
                "choices": choices,
                "choice_labels": choice_labels,
                "multi_select": is_multi,
                "editable_choice": bool(flags & (1 << 18)),
                "read_only": is_read_only or is_sig,
                "is_signature": is_sig,
            })
    return fields


def update_form_fields(doc: fitz.Document, field_dict: dict[str, Any]) -> int:
    """Actualiza de forma atómica los valores de los campos dados en `{nombre_campo: valor}` (H21, H22, N02).

    - Omite campos de solo lectura y firmas digitales.
    - Soporta `ListBox` multiselección (`list[str]`) escribiendo `/V` e `/I` en el PDF.
    - No silencia errores de `w.update()`: si un widget falla, revierte los widgets previos y propaga la excepción.
    """
    count = 0
    multi_flag = getattr(fitz, "PDF_CH_FIELD_IS_MULTI_SELECT", 1 << 21)
    edit_flag = getattr(fitz, "PDF_CH_FIELD_IS_EDIT", 1 << 18)
    # Restaurar diccionarios completos (/I, /V, padres y recursos), no sólo /V.
    # Los streams originales de apariencia también pueden ser modificados por update().
    objects = {x: doc.xref_object(x) for x in range(1, doc.xref_length())}
    streams = {x: doc.xref_stream_raw(x) for x in objects
               if doc.xref_is_stream(x) and doc.xref_get_key(x, "Subtype")[1] == "/Form"}

    try:
        for pno, page in enumerate(doc):
            for w in page.widgets():
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    continue
                flags = getattr(w, "field_flags", 0) or 0
                if flags & fitz.PDF_FIELD_IS_READ_ONLY:
                    continue

                if w.field_name not in field_dict:
                    continue

                new_val = field_dict[w.field_name]
                choices = _normalize_choices(getattr(w, "choice_values", None))

                if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    w.field_value = bool(new_val)
                    w.update()
                elif w.field_type in (fitz.PDF_WIDGET_TYPE_LISTBOX, fitz.PDF_WIDGET_TYPE_COMBOBOX):
                    if isinstance(new_val, (list, tuple)):
                        str_vals = [str(x) for x in new_val]
                        if choices:
                            for sv in str_vals:
                                if sv not in choices:
                                    raise ValueError(f"Valor '{sv}' no válido para el campo '{w.field_name}'.")
                        w.field_value = str_vals[0] if str_vals else ""
                        w.update()
                        arr_str = "[" + " ".join(fitz.get_pdf_str(sv) for sv in str_vals) + "]"
                        doc.xref_set_key(w.xref, "V", arr_str)
                        if choices:
                            idxs = sorted(choices.index(sv) for sv in str_vals if sv in choices)
                            idx_str = "[" + " ".join(str(i) for i in idxs) + "]"
                            doc.xref_set_key(w.xref, "I", idx_str)
                    else:
                        sval = str(new_val)
                        if choices and not (flags & edit_flag) and sval and sval not in choices:
                            raise ValueError(f"Valor '{sval}' no válido para el campo '{w.field_name}'.")
                        w.field_value = sval
                        w.update()
                else:
                    w.field_value = str(new_val)
                    w.update()

                count += 1
    except Exception:
        # update() puede crear nuevos streams de apariencia. No conservar datos de la
        # edición rechazada en objetos huérfanos aunque el llamador guarde sin garbage.
        for xref in range(len(objects) + 1, doc.xref_length()):
            if doc.xref_is_stream(xref):
                doc.update_stream(xref, b"", compress=False)
            doc.update_object(xref, "null")
        for xref, raw in objects.items():
            doc.update_object(xref, raw)
        for xref, data in streams.items():
            doc.update_stream(xref, data, compress=False)
            doc.update_object(xref, objects[xref])
        raise

    return count


def flatten_forms(doc: fitz.Document, keep_annotations: bool = True) -> None:
    """Aplana los campos de formulario convirtiéndolos en texto y gráficos fijos.

    Una vez aplanado, los campos ya no se pueden modificar digitalmente.
    """
    doc.bake(annots=not keep_annotations, widgets=True)
