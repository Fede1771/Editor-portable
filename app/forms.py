"""
Módulo para gestión, rellenado y aplanado de formularios PDF (AcroForms) y protección de firmas.
"""
from typing import Any
import pymupdf as fitz


def document_has_signatures(doc: fitz.Document) -> bool:
    """Verifica si el documento contiene firmas digitales criptográficas."""
    try:
        flags = doc.get_sigflags()
        if flags > 0:
            return True
        for page in doc:
            for w in page.widgets():
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE or getattr(w, "is_signed", False):
                    return True
    except Exception:
        pass
    return False


def get_form_fields(doc: fitz.Document) -> list[dict[str, Any]]:
    """Obtiene todos los campos de formulario presentes en el PDF con sus valores actuales."""
    fields = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for w in page.widgets():
            ft = w.field_type_string
            val = w.field_value
            choices = []
            if hasattr(w, "choice_values") and w.choice_values:
                choices = list(w.choice_values)

            is_sig = (w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE)
            is_read_only = bool(w.field_flags & fitz.PDF_FIELD_IS_READ_ONLY) if hasattr(w, "field_flags") else False

            fields.append({
                "page": page_idx,
                "name": w.field_name or f"Campo_P{page_idx+1}",
                "label": w.field_label or w.field_name or "",
                "type": "Signature" if is_sig else ft,
                "value": val,
                "rect": w.rect,
                "choices": choices,
                "read_only": is_read_only or is_sig,
                "is_signature": is_sig,
            })
    return fields


def update_form_fields(doc: fitz.Document, field_dict: dict[str, Any]) -> int:
    """Actualiza los valores de los campos dados en un diccionario {nombre_campo: valor}.

    Retorna la cantidad de campos actualizados (omitiendo campos de solo lectura y firmas digitales).
    """
    count = 0
    for page in doc:
        for w in page.widgets():
            if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                continue
            if hasattr(w, "field_flags") and (w.field_flags & fitz.PDF_FIELD_IS_READ_ONLY):
                continue

            if w.field_name in field_dict:
                new_val = field_dict[w.field_name]
                if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    w.field_value = bool(new_val)
                elif w.field_type in (fitz.PDF_WIDGET_TYPE_LISTBOX, fitz.PDF_WIDGET_TYPE_COMBOBOX):
                    w.field_value = str(new_val)
                else:
                    w.field_value = str(new_val)
                try:
                    w.update()
                    count += 1
                except Exception:
                    pass
    return count


def flatten_forms(doc: fitz.Document, keep_annotations: bool = True) -> None:
    """Aplana los campos de formulario convirtiéndolos en texto y gráficos fijos.

    Una vez aplanado, los campos ya no se pueden modificar digitalmente.
    """
    doc.bake(annots=not keep_annotations, widgets=True)
