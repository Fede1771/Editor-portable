"""
Módulo para gestión, rellenado y aplanado de formularios PDF (AcroForms).
"""
from typing import Any
import pymupdf as fitz


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

            fields.append({
                "page": page_idx,
                "name": w.field_name or f"Campo_P{page_idx+1}",
                "label": w.field_label or w.field_name or "",
                "type": ft,
                "value": val,
                "rect": w.rect,
                "choices": choices,
            })
    return fields


def update_form_fields(doc: fitz.Document, field_dict: dict[str, Any]) -> int:
    """Actualiza los valores de los campos dados en un diccionario {nombre_campo: valor}.

    Retorna la cantidad de campos actualizados.
    """
    count = 0
    for page in doc:
        for w in page.widgets():
            if w.field_name in field_dict:
                new_val = field_dict[w.field_name]
                # Normalizar bool para checkboxes
                if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    w.field_value = bool(new_val)
                else:
                    w.field_value = str(new_val)
                w.update()
                count += 1
    return count


def flatten_forms(doc: fitz.Document, keep_annotations: bool = True) -> None:
    """Aplana los campos de formulario convirtiéndolos en texto y gráficos fijos.

    Una vez aplanado, los campos ya no se pueden modificar digitalmente.
    """
    doc.bake(annots=not keep_annotations, widgets=True)
