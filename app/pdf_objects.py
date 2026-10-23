"""Lectura estructural de objetos PDF; nunca buscar claves dentro de strings."""
from __future__ import annotations

from io import BytesIO
import re
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, read_object

_INDIRECT_REF_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+R\s*$")

MAX_OBJECT_BYTES = 262_144
MAX_OBJECT_DEPTH = 64
MAX_OBJECT_ELEMENTS = 5_000
MAX_TRAVERSAL_NODES = 10_000


class PdfObjectLimitError(ValueError):
    """Excepción lanzada cuando un objeto PDF supera los límites estructurales de seguridad (V04)."""


class _ObjectContext:
    strict = True

    def get_object(self, reference):
        raise ValueError("Las referencias PDF deben resolverse explícitamente.")


_CONTEXT = _ObjectContext()


def _check_raw_limits(raw: str) -> bytes:
    data = (raw or "").encode("utf-8")
    if len(data) > MAX_OBJECT_BYTES:
        raise PdfObjectLimitError("El objeto PDF supera el límite de tamaño permitido.")
    depth = 0
    in_str = 0
    escape = False
    in_comment = False
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if in_comment:
            if b in (10, 13):
                in_comment = False
            i += 1
            continue
        if in_str > 0:
            if escape:
                escape = False
            elif b == 92:  # '\\'
                escape = True
            elif b == 40:  # '('
                in_str += 1
            elif b == 41:  # ')'
                in_str -= 1
            i += 1
            continue
        if b == 37:  # '%'
            in_comment = True
            i += 1
            continue
        if b == 40:  # '('
            in_str = 1
            i += 1
            continue
        if b == 91:  # '['
            depth += 1
            if depth > MAX_OBJECT_DEPTH:
                raise PdfObjectLimitError("El objeto PDF supera la profundidad máxima permitida.")
        elif b == 93:  # ']'
            depth = max(0, depth - 1)
        elif b == 60 and i + 1 < n and data[i + 1] == 60:  # '<<'
            depth += 1
            if depth > MAX_OBJECT_DEPTH:
                raise PdfObjectLimitError("El objeto PDF supera la profundidad máxima permitida.")
            i += 2
            continue
        elif b == 62 and i + 1 < n and data[i + 1] == 62:  # '>>'
            depth = max(0, depth - 1)
            i += 2
            continue
        i += 1
    return data


def _check_parsed_limits(obj) -> None:
    stack = [(obj, 1)]
    elements = 0
    while stack:
        cur, depth = stack.pop()
        if depth > MAX_OBJECT_DEPTH:
            raise PdfObjectLimitError("El objeto PDF supera la profundidad máxima permitida.")
        if isinstance(cur, ArrayObject):
            elements += len(cur)
            if elements > MAX_OBJECT_ELEMENTS:
                raise PdfObjectLimitError("El objeto PDF supera el límite de elementos permitido.")
            for item in cur:
                if isinstance(item, (ArrayObject, DictionaryObject)):
                    stack.append((item, depth + 1))
        elif isinstance(cur, DictionaryObject):
            elements += len(cur)
            if elements > MAX_OBJECT_ELEMENTS:
                raise PdfObjectLimitError("El objeto PDF supera el límite de elementos permitido.")
            for k, v in cur.items():
                if isinstance(v, (ArrayObject, DictionaryObject)):
                    stack.append((v, depth + 1))


def parse_object(raw: str):
    data = _check_raw_limits(raw)
    m = _INDIRECT_REF_RE.match(raw or "")
    if m:
        return IndirectObject(int(m.group(1)), int(m.group(2)), _CONTEXT)
    parsed = read_object(BytesIO(data), _CONTEXT)
    _check_parsed_limits(parsed)
    return parsed


parse_pdf_object = parse_object


def resolve(doc, obj):
    visited = set()
    while isinstance(obj, IndirectObject):
        if obj.idnum in visited:
            raise ValueError("Referencia circular en un objeto PDF.")
        if len(visited) >= MAX_TRAVERSAL_NODES:
            raise ValueError("La cadena de referencias PDF supera el límite permitido.")
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


def decode_pdf_bytes(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith((b"\xfe\xff", b"\xff\xfe")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def get_text_representations(doc, xref: int, key: str) -> list[str]:
    """Obtiene todas las representaciones textuales de `key` en `xref`, incluyendo cadenas y streams."""
    kind, raw = doc.xref_get_key(xref, key)
    if kind == "null":
        return []
    if kind == "string":
        return [raw]
    out: list[str] = []
    visited_xrefs: set[int] = set()

    def _collect(obj) -> None:
        if len(visited_xrefs) > MAX_TRAVERSAL_NODES:
            return
        if isinstance(obj, IndirectObject):
            if obj.idnum in visited_xrefs or obj.idnum <= 0:
                return
            visited_xrefs.add(obj.idnum)
            if doc.xref_is_stream(obj.idnum):
                try:
                    out.append(decode_pdf_bytes(doc.xref_stream(obj.idnum) or b""))
                except Exception:
                    pass
            try:
                _collect(parse_object(doc.xref_object(obj.idnum)))
            except Exception:
                pass
            return
        if isinstance(obj, (bytes, bytearray)):
            out.append(decode_pdf_bytes(bytes(obj)))
        elif isinstance(obj, str):
            out.append(obj)
        elif isinstance(obj, ArrayObject):
            for item in obj:
                _collect(item)
        elif isinstance(obj, DictionaryObject):
            for val in obj.values():
                _collect(val)

    try:
        _collect(parse_object(raw))
    except Exception:
        out.append(raw)
    return [t for t in out if t]


def set_pdf_key_null(doc, xref: int, key_path: str) -> None:
    """Elimina `key_path` resolviendo referencias indirectas intermedias para evitar el bug de ruta de MuPDF."""
    parts = [p for p in key_path.split("/") if p]
    if not parts:
        return
    cur_xref = xref
    prefix: list[str] = []
    for part in parts[:-1]:
        sub_key = "/".join(prefix + [part])
        kind, val = doc.xref_get_key(cur_xref, sub_key)
        if kind == "xref":
            cur_xref = int(val.split()[0])
            prefix = []
        elif kind == "null":
            return
        else:
            prefix.append(part)
    final_key = "/".join(prefix + [parts[-1]])
    doc.xref_set_key(cur_xref, final_key, "null")


def array_strings(raw: str) -> list[str]:
    value = parse_object(raw)
    if not isinstance(value, ArrayObject) or any(not isinstance(x, str) for x in value):
        raise ValueError("El campo contiene una selección PDF no representable.")
    return [str(x).lstrip("/") if isinstance(x, NameObject) else str(x) for x in value]


def field_chain(doc, xref: int):
    """Widget y padres lógicos, sin seguir enlaces a páginas u otros campos."""
    visited = set()
    while xref and xref not in visited:
        if len(visited) >= MAX_TRAVERSAL_NODES:
            raise ValueError("La jerarquía de campos supera el límite permitido.")
        visited.add(xref)
        yield xref
        kind, raw = doc.xref_get_key(xref, "Parent")
        xref = int(raw.split()[0]) if kind == "xref" else 0


def iter_outline_xrefs(doc) -> list[int]:
    """Recorre todos los objetos indirectos alcanzables en el árbol /Outlines (marcadores)."""
    cat = doc.pdf_catalog()
    kind, raw = doc.xref_get_key(cat, "Outlines")
    if kind == "null":
        return []
    pending: list[int] = []
    if kind == "xref":
        pending.append(int(raw.split()[0]))
    elif kind == "dict":
        obj = parse_object(raw)
        if isinstance(obj, DictionaryObject):
            for k in ("/First", "/Last"):
                v = obj.get(k)
                if isinstance(v, IndirectObject):
                    pending.append(v.idnum)
    visited: set[int] = set()
    ordered: list[int] = []
    while pending:
        if len(visited) >= MAX_TRAVERSAL_NODES:
            raise ValueError("El árbol de marcadores supera el límite de inspección.")
        cur = pending.pop()
        if cur <= 0 or cur in visited:
            continue
        visited.add(cur)
        ordered.append(cur)
        for nav in ("First", "Last", "Next", "Prev"):
            nk, nv = doc.xref_get_key(cur, nav)
            if nk == "xref":
                nxt = int(nv.split()[0])
                if nxt not in visited:
                    pending.append(nxt)
    return ordered


def iter_acroform_field_xrefs(doc) -> list[int]:
    """Recorre todos los nodos alcanzables en /AcroForm/Fields y sus listas /Kids y /Parent."""
    cat = doc.pdf_catalog()
    fields_val = get_value(doc, cat, "AcroForm/Fields")
    if not isinstance(fields_val, ArrayObject):
        return []
    pending: list[int] = [item.idnum for item in fields_val if isinstance(item, IndirectObject)]
    visited: set[int] = set()
    ordered: list[int] = []
    while pending:
        if len(visited) >= MAX_TRAVERSAL_NODES:
            raise ValueError("El árbol AcroForm/Fields supera el límite de inspección.")
        cur = pending.pop()
        if cur <= 0 or cur in visited:
            continue
        visited.add(cur)
        ordered.append(cur)
        pk, pv = doc.xref_get_key(cur, "Parent")
        if pk == "xref":
            px = int(pv.split()[0])
            if px not in visited:
                pending.append(px)
        kids = get_value(doc, cur, "Kids")
        if isinstance(kids, ArrayObject):
            for k in kids:
                if isinstance(k, IndirectObject) and k.idnum not in visited:
                    pending.append(k.idnum)
    return ordered

