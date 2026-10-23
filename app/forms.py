"""
Módulo para gestión, rellenado y aplanado de formularios PDF (AcroForms) y protección de firmas.
"""
from __future__ import annotations

import re
from typing import Any
import pymupdf as fitz


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
    """Extrae cadenas literales (...) o nombres /Name de un array PDF como '[(A)(B)]'."""
    items: list[str] = []
    # Buscar literales entre paréntesis o nombres /Token
    for m in re.finditer(r"\((?:\\.|[^\\)])*\)|/([^\s\[\]()<>/{}%]+)", raw_array):
        tok = m.group(0)
        if tok.startswith("(") and tok.endswith(")"):
            inner = tok[1:-1]
            inner = inner.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
            items.append(inner)
        elif m.group(1):
            items.append(m.group(1))
    return items


def _escape_pdf_string(val: str) -> str:
    return val.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


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
            choices = _normalize_choices(getattr(w, "choice_values", None))

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
                "multi_select": is_multi,
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
    applied_backups: list[tuple[int, int, Any, tuple[str, str]]] = []

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
                prev_v = doc.xref_get_key(w.xref, "V")
                prev_fval = w.field_value
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
                        arr_str = "[" + "".join(f"({_escape_pdf_string(sv)})" for sv in str_vals) + "]"
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

                applied_backups.append((pno, w.xref, prev_fval, prev_v))
                count += 1
    except Exception:
        # Revertir los cambios parciales aplicados antes del fallo (N02)
        for pno, xref, prev_fval, (vk, vv) in reversed(applied_backups):
            try:
                for rw in doc[pno].widgets():
                    if rw.xref == xref:
                        rw.field_value = prev_fval
                        try:
                            rw.update()
                        except Exception:
                            pass
                        break
                if vk == "null":
                    doc.xref_set_key(xref, "V", "null")
                elif vk in ("string", "name", "array", "int", "bool"):
                    doc.xref_set_key(xref, "V", vv)
            except Exception:
                pass
        raise

    return count


def flatten_forms(doc: fitz.Document, keep_annotations: bool = True) -> None:
    """Aplana los campos de formulario convirtiéndolos en texto y gráficos fijos.

    Una vez aplanado, los campos ya no se pueden modificar digitalmente.
    """
    doc.bake(annots=not keep_annotations, widgets=True)
