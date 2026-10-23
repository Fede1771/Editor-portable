"""Lectura estructural de objetos PDF; nunca buscar claves dentro de strings."""
from __future__ import annotations

from io import BytesIO
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, read_object


class _ObjectContext:
    strict = True

    def get_object(self, reference):
        raise ValueError("Las referencias PDF deben resolverse explícitamente.")


_CONTEXT = _ObjectContext()


def parse_object(raw: str):
    return read_object(BytesIO(raw.encode("utf-8")), _CONTEXT)


def resolve(doc, obj):
    visited = set()
    while isinstance(obj, IndirectObject):
        if obj.idnum in visited:
            raise ValueError("Referencia circular en un objeto PDF.")
        visited.add(obj.idnum)
        obj = parse_object(doc.xref_object(obj.idnum))
    return obj


def get_value(doc, xref: int, key: str):
    kind, value = doc.xref_get_key(xref, key)
    if kind == "null":
        return None
    if kind == "string":
        return value
    return resolve(doc, parse_object(value))


def array_strings(raw: str) -> list[str]:
    value = parse_object(raw)
    if not isinstance(value, ArrayObject) or any(not isinstance(x, str) for x in value):
        raise ValueError("El campo contiene una selección PDF no representable.")
    return [str(x).lstrip("/") if isinstance(x, NameObject) else str(x) for x in value]


def field_chain(doc, xref: int):
    """Widget y padres lógicos, sin seguir enlaces a páginas u otros campos."""
    visited = set()
    while xref and xref not in visited:
        visited.add(xref)
        yield xref
        kind, raw = doc.xref_get_key(xref, "Parent")
        xref = int(raw.split()[0]) if kind == "xref" else 0
