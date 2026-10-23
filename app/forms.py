"""
Módulo para gestión, rellenado y aplanado de formularios PDF (AcroForms) y protección de firmas.
"""
from __future__ import annotations

from typing import Any
import pymupdf as fitz
from .pdf_objects import (
    ArrayObject, DictionaryObject, IndirectObject, NameObject,
    array_strings, field_chain, get_value, iter_acroform_field_xrefs, parse_object,
)

_SIG_DICT_KEYS = {"/ByteRange", "/Contents", "/SubFilter", "/Cert", "/Reference"}


def _is_sig_dict_object(doc: fitz.Document, obj: Any) -> bool:
    if isinstance(obj, DictionaryObject):
        if any(k in obj for k in _SIG_DICT_KEYS):
            return True
        t = obj.get("/Type")
        if isinstance(t, NameObject) and str(t) in {"/Sig", "/DocTimeStamp"} and len(obj) > 1:
            return True
    return False


def _xref_has_sig_dict(doc: fitz.Document, xref: int, *, is_sig_ft: bool = False) -> bool:
    """Comprueba si el objeto `xref` (o su cadena de padres) posee un diccionario de firma aplicado (V05)."""
    for cur in field_chain(doc, xref):
        kind, val = doc.xref_get_key(cur, "V")
        if kind == "null":
            continue
        if kind == "dict":
            if any(tok in val for tok in ("/ByteRange", "/Contents", "/SubFilter", "/Cert", "/Reference")):
                return True
            if is_sig_ft and val.strip() not in ("<<>>", "<< >>", ""):
                return True
        elif kind == "xref":
            try:
                v_xref = int(val.split()[0])
                v_obj = doc.xref_object(v_xref) or ""
                if any(tok in v_obj for tok in ("/ByteRange", "/Contents", "/SubFilter", "/Cert", "/Reference")):
                    return True
                if is_sig_ft and v_obj.strip() not in ("null", "<<>>", "<< >>", ""):
                    return True
            except Exception:
                return True
        elif is_sig_ft:
            return True
    return False


def _xref_effective_ft(doc: fitz.Document, xref: int) -> str:
    for cur in field_chain(doc, xref):
        kind, val = doc.xref_get_key(cur, "FT")
        if kind != "null" and val:
            return val.strip()
    return ""


def inspect_signatures(doc: fitz.Document) -> dict[str, Any]:
    """Inspecciona widgets, árbol canónico /AcroForm/Fields y /Perms del catálogo (V05).

    Registra por separado la presencia de campos/firmas aplicadas y deja constancia explícita
    de que no se realiza validación criptográfica de certificados o cadenas de confianza.
    """
    sig_field_xrefs: set[int] = set()
    signed_roots: set[int] = set()
    empty_roots: set[int] = set()
    catalog_perms = False
    unsupported = False

    try:
        for page in doc:
            try:
                page_widgets = list(page.widgets())
            except Exception:
                page_widgets = []
            for w in page_widgets:
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    chain = list(field_chain(doc, w.xref))
                    root = chain[-1] if chain else w.xref
                    sig_field_xrefs.add(root)
                    if getattr(w, "is_signed", False) or _xref_has_sig_dict(doc, w.xref, is_sig_ft=True):
                        signed_roots.add(root)
                    else:
                        empty_roots.add(root)

        for xref in iter_acroform_field_xrefs(doc):
            chain = list(field_chain(doc, xref))
            root = chain[-1] if chain else xref
            ft = _xref_effective_ft(doc, xref)
            if ft == "/Sig":
                sig_field_xrefs.add(root)
                if _xref_has_sig_dict(doc, xref, is_sig_ft=True):
                    signed_roots.add(root)
                elif root not in signed_roots:
                    empty_roots.add(root)
            elif _xref_has_sig_dict(doc, xref, is_sig_ft=False):
                sig_field_xrefs.add(root)
                signed_roots.add(root)

        cat = doc.pdf_catalog()
        perms_kind, perms_raw = doc.xref_get_key(cat, "Perms")
        if perms_kind != "null":
            perms_obj = get_value(doc, cat, "Perms")
            if isinstance(perms_obj, DictionaryObject):
                for v in perms_obj.values():
                    resolved = get_value(doc, v.idnum, "") if isinstance(v, IndirectObject) else v
                    if isinstance(v, IndirectObject):
                        try:
                            resolved = parse_object(doc.xref_object(v.idnum))
                        except Exception:
                            unsupported = True
                    if _is_sig_dict_object(doc, resolved) or len(perms_obj) > 0:
                        catalog_perms = True
            else:
                catalog_perms = True

        try:
            sigflags = int(doc.get_sigflags() or 0)
        except Exception:
            sigflags = 0
        if sigflags > 0 and not sig_field_xrefs and not catalog_perms:
            unsupported = True
    except Exception:
        unsupported = True

    empty_roots -= signed_roots
    has_applied = bool(signed_roots or catalog_perms or unsupported)
    has_fields = bool(sig_field_xrefs or has_applied)
    return {
        "has_signature_fields": has_fields,
        "has_applied_signatures": has_applied,
        "signature_count": len(signed_roots) + (1 if catalog_perms and not signed_roots else 0),
        "empty_field_count": len(empty_roots),
        "catalog_perms": catalog_perms,
        "unsupported_structure": unsupported,
        "certificate_validation": "not_performed",
    }


def has_signature_fields(doc: fitz.Document) -> bool:
    """Indica si el documento contiene al menos un campo o estructura de firma (/FT /Sig)."""
    return inspect_signatures(doc)["has_signature_fields"]


def document_has_signatures(doc: fitz.Document) -> bool:
    """Verifica si el documento contiene firmas digitales aplicadas o estructuras firmadas (N04 / H49 / V05)."""
    return inspect_signatures(doc)["has_applied_signatures"]


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


def _canonical_field_owner(doc: fitz.Document, xref: int) -> int:
    chain = list(field_chain(doc, xref))
    return chain[-1] if chain else xref


def _get_xref_v_array(doc: fitz.Document, xref: int) -> list[str] | None:
    chain = list(field_chain(doc, xref))
    for cur in reversed(chain):
        kind, val = doc.xref_get_key(cur, "V")
        if kind == "array":
            return _parse_pdf_array_strings(val)
    return None


def normalize_field_value(field_meta: dict[str, Any], val: Any) -> Any:
    """Normaliza la representación de un valor de campo según su tipo (O01)."""
    ftype = field_meta.get("type", "")
    if ftype == "CheckBox":
        return bool(val) and str(val).strip("/") not in ("Off", "No", "False", "0", "")
    if ftype == "ListBox" and field_meta.get("multi_select"):
        if isinstance(val, (list, tuple)):
            return [str(x) for x in val]
        return [str(val)] if val else []
    if isinstance(val, (list, tuple)):
        return str(val[0]) if val else ""
    return str(val or "")


def _sync_listbox_appearance(doc: fitz.Document, w: fitz.Widget, selected_indices: list[int]) -> None:
    """Sincroniza el stream de apariencia /AP/N del ListBox con las filas seleccionadas (V09)."""
    try:
        kind, raw = doc.xref_get_key(w.xref, "AP/N")
        if kind != "xref":
            return
        ap_xref = int(raw.split()[0])
        if not doc.xref_is_stream(ap_xref):
            return
        stream_data = doc.xref_stream(ap_xref) or b""
        text = stream_data.decode("latin-1", errors="replace")
        # Eliminar bloques previos de selección si existían
        lines = [ln for ln in text.splitlines() if not ln.endswith("%editorpdf_sel")]
        if selected_indices and "BT" in lines:
            bt_pos = lines.index("BT")
            rect_h = max(10.0, float(w.rect.height))
            rect_w = max(10.0, float(w.rect.width))
            row_h = 13.392
            hl_lines = []
            for idx in selected_indices:
                y = rect_h - (idx + 1) * row_h
                if y + row_h > 0 and y < rect_h:
                    hl_lines.append(
                        f"q 0.75 0.86 0.98 rg 1 {max(1.0, y):.2f} {max(2.0, rect_w - 2.0):.2f} {row_h:.2f} re f Q %editorpdf_sel"
                    )
            lines = lines[:bt_pos] + hl_lines + lines[bt_pos:]
        doc.update_stream(ap_xref, ("\n".join(lines) + "\n").encode("latin-1", errors="replace"))
    except Exception:
        pass


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

            if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                ft = "CheckBox"
                val = bool(val) and str(val).strip("/") not in ("Off", "No", "False", "0", "")
            elif w.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX:
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
    """Actualiza de forma atómica los valores de los campos dados en `{nombre_campo: valor}` (H21, H22, N02, V09).

    - Omite campos de solo lectura y firmas digitales.
    - Actualiza `/V` e `/I` en el campo lógico canónico sin dejar overrides contradictorios en los widgets hijos.
    - Sincroniza apariencias de todos los widgets asociados y revierte completamente ante fallo.
    """
    count = 0
    edit_flag = getattr(fitz, "PDF_CH_FIELD_IS_EDIT", 1 << 18)
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
                chain = list(field_chain(doc, w.xref))
                owner_xref = chain[-1] if chain else w.xref

                if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    checked = bool(new_val) and str(new_val).strip("/") not in ("Off", "No", "False", "0", "")
                    w.field_value = checked
                    w.update()
                    state_name = "/Yes" if checked else "/Off"
                    doc.xref_set_key(owner_xref, "V", state_name)
                    doc.xref_set_key(w.xref, "AS", state_name)
                    for child_xref in chain[:-1]:
                        doc.xref_set_key(child_xref, "V", "null")
                elif w.field_type in (fitz.PDF_WIDGET_TYPE_LISTBOX, fitz.PDF_WIDGET_TYPE_COMBOBOX):
                    had_widget_opt = doc.xref_get_key(w.xref, "Opt")[0] != "null"
                    owner_opt_kind, owner_opt_val = doc.xref_get_key(owner_xref, "Opt")
                    if w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX and w.xref != owner_xref and not had_widget_opt and owner_opt_kind != "null":
                        doc.xref_set_key(w.xref, "Opt", owner_opt_val)

                    if isinstance(new_val, (list, tuple)):
                        str_vals = [str(x) for x in new_val]
                        if choices:
                            for sv in str_vals:
                                if sv not in choices:
                                    raise ValueError(f"Valor '{sv}' no válido para el campo '{w.field_name}'.")
                        w.field_value = str_vals[0] if str_vals else ""
                        w.update()
                        arr_str = "[" + " ".join(fitz.get_pdf_str(sv) for sv in str_vals) + "]"
                        doc.xref_set_key(owner_xref, "V", arr_str)
                        idxs: list[int] = []
                        if choices:
                            idxs = sorted(choices.index(sv) for sv in str_vals if sv in choices)
                            idx_str = "[" + " ".join(str(i) for i in idxs) + "]"
                            doc.xref_set_key(owner_xref, "I", idx_str)
                        else:
                            doc.xref_set_key(owner_xref, "I", "null")
                        for child_xref in chain[:-1]:
                            doc.xref_set_key(child_xref, "V", "null")
                            doc.xref_set_key(child_xref, "I", "null")
                        if w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX and w.xref != owner_xref and not had_widget_opt:
                            doc.xref_set_key(w.xref, "Opt", "null")
                        if w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX:
                            _sync_listbox_appearance(doc, w, idxs)
                    else:
                        sval = str(new_val)
                        if choices and not (flags & edit_flag) and sval and sval not in choices:
                            raise ValueError(f"Valor '{sval}' no válido para el campo '{w.field_name}'.")
                        w.field_value = sval
                        w.update()
                        doc.xref_set_key(owner_xref, "V", fitz.get_pdf_str(sval))
                        if choices and sval in choices:
                            doc.xref_set_key(owner_xref, "I", f"[{choices.index(sval)}]")
                        else:
                            doc.xref_set_key(owner_xref, "I", "null")
                        for child_xref in chain[:-1]:
                            doc.xref_set_key(child_xref, "V", "null")
                            doc.xref_set_key(child_xref, "I", "null")
                        if w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX and w.xref != owner_xref and not had_widget_opt:
                            doc.xref_set_key(w.xref, "Opt", "null")
                        if sval == "":
                            try:
                                fitz.mupdf.pdf_dirty_annot(w._annot.this)
                                fitz.mupdf.pdf_update_annot(w._annot.this)
                            except Exception:
                                pass
                        elif w.field_type == fitz.PDF_WIDGET_TYPE_LISTBOX and choices and sval in choices:
                            _sync_listbox_appearance(doc, w, [choices.index(sval)])
                else:
                    sval = str(new_val)
                    w.field_value = sval
                    w.update()
                    doc.xref_set_key(owner_xref, "V", fitz.get_pdf_str(sval))
                    for child_xref in chain[:-1]:
                        doc.xref_set_key(child_xref, "V", "null")
                    if sval == "":
                        try:
                            fitz.mupdf.pdf_dirty_annot(w._annot.this)
                            fitz.mupdf.pdf_update_annot(w._annot.this)
                        except Exception:
                            pass

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
