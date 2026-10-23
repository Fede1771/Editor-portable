"""Inspección textual de todas las apariencias con recursos y fuentes reales."""
from __future__ import annotations

import math
import pymupdf as fitz

from .document_io import clone_pdf
from .pdf_objects import ArrayObject, DictionaryObject, MAX_TEXT_BYTES, appearance_streams, get_value


class AppearanceInspector:
    """Extrae texto de Form XObjects en una copia aislada, sin activar acciones."""

    def __init__(self, doc: fitz.Document):
        self.source = doc
        self.copy = None
        self.page = None
        self.resources = None
        self.content = None
        self.cache: dict[tuple[int, int], str] = {}
        self.locations = {entry[0]: page.xref for page in doc for entry in page.annot_xrefs()}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.copy is not None:
            self.copy.close()

    def texts(self, annot_xref: int) -> list[str]:
        return [self._text(stream, self.locations.get(annot_xref, 0))
                for stream in appearance_streams(self.source, annot_xref)]

    def _text(self, stream: int, source_page: int) -> str:
        key = (stream, source_page)
        if key in self.cache:
            return self.cache[key]
        bbox = get_value(self.source, stream, "BBox")
        if (not isinstance(bbox, ArrayObject) or len(bbox) != 4
                or self.source.xref_get_key(stream, "Subtype")[1] != "/Form"):
            raise ValueError("No se puede inspeccionar una apariencia sin un Form/BBox válido.")
        matrix = get_value(self.source, stream, "Matrix")
        if matrix is not None and (not isinstance(matrix, ArrayObject) or len(matrix) != 6):
            raise ValueError("Matriz de apariencia PDF inválida.")
        bounds = fitz.Rect(*map(float, bbox))
        if matrix is not None:
            bounds = bounds * fitz.Matrix(*map(float, matrix))
        bounds.normalize()
        if bounds.is_empty or not all(math.isfinite(v) for v in bounds):
            raise ValueError("Dimensiones de apariencia PDF inválidas.")
        if self.copy is None:
            self.copy = clone_pdf(self.source)
            self.page = self.copy.new_page(width=1, height=1)
            self.resources = self.copy.get_new_xref()
            self.content = self.copy.get_new_xref()
            self.copy.update_object(self.content, "<< >>")
            self.copy.update_stream(self.content, b"")
            self.page.set_contents(self.content)
            self.copy.xref_set_key(self.page.xref, "Resources", f"{self.resources} 0 R")
        # Los recursos de un Form pueden heredarse de la página contenedora.
        fallback = "<< >>"
        seen = set()
        while source_page and source_page not in seen:
            seen.add(source_page)
            kind, raw = self.source.xref_get_key(source_page, "Resources")
            if kind != "null":
                fallback = self.source.xref_object(int(raw.split()[0])) if kind == "xref" else raw
                break
            kind, raw = self.source.xref_get_key(source_page, "Parent")
            source_page = int(raw.split()[0]) if kind == "xref" else 0
        self.copy.update_object(self.resources, fallback)
        # Preservar los XObjects heredados y no modificar su diccionario compartido.
        xobjects = get_value(self.copy, self.resources, "XObject")
        if xobjects is not None and not isinstance(xobjects, DictionaryObject):
            raise ValueError("Diccionario de recursos XObject inválido.")
        alias = "EditorAppearance"
        while xobjects is not None and "/" + alias in xobjects:
            alias += "_"
        kind, raw = self.copy.xref_get_key(self.resources, "XObject")
        if kind == "xref":
            raw = self.copy.xref_object(int(raw.split()[0]))
        self.copy.xref_set_key(self.resources, "XObject", raw if xobjects is not None else "<< >>")
        self.copy.xref_set_key(self.resources, "XObject/" + alias, f"{stream} 0 R")
        self.copy.update_stream(self.content, f"q /{alias} Do Q".encode("ascii"))
        self.copy.xref_set_key(self.page.xref, "MediaBox", "[" + " ".join(map(str, bounds)) + "]")
        self.page = self.copy.reload_page(self.page)
        text = self.page.get_text("text", clip=fitz.INFINITE_RECT(),
                                  flags=fitz.TEXTFLAGS_TEXT & ~fitz.TEXT_MEDIABOX_CLIP)
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("La apariencia supera el límite de texto inspeccionable.")
        self.cache[key] = text
        return text
