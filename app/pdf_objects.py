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
MAX_TEXT_BYTES = 4 * 1024 * 1024


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
        return data.decode("utf-16")
    if data.startswith(b"\x00<"):
        return data.decode("utf-16-be")
    if data.startswith(b"<\x00"):
        return data.decode("utf-16-le")
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

    pending = [parse_object(raw)]
    count = 0
    text_bytes = 0
    while pending:
        count += 1
        if count > MAX_TRAVERSAL_NODES:
            raise PdfObjectLimitError("La representación textual supera el límite de inspección.")
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            if obj.idnum in visited_xrefs:
                continue
            if obj.idnum <= 0:
                raise ValueError("Referencia textual PDF inválida.")
            visited_xrefs.add(obj.idnum)
            if doc.xref_is_stream(obj.idnum):
                data = doc.xref_stream(obj.idnum) or b""
                text_bytes += len(data)
                if text_bytes > MAX_TEXT_BYTES:
                    raise PdfObjectLimitError("El texto alternativo supera el límite de inspección.")
                out.append(decode_pdf_bytes(data))
            else:
                pending.append(parse_object(doc.xref_object(obj.idnum)))
        elif isinstance(obj, (bytes, bytearray)):
            out.append(decode_pdf_bytes(bytes(obj)))
        elif isinstance(obj, str):
            out.append(obj)
        elif isinstance(obj, ArrayObject):
            pending.extend(obj)
        elif isinstance(obj, DictionaryObject):
            pending.extend(obj.values())
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


def terminal_field_owner(doc, xref: int) -> int | None:
    """El campo terminal más cercano; nunca convertir un grupo de campos en un valor."""
    for cur in field_chain(doc, xref):
        subtype = doc.xref_get_key(cur, "Subtype")[1]
        named = doc.xref_get_key(cur, "T")[0] != "null"
        typed = doc.xref_get_key(cur, "FT")[0] != "null"
        parent = doc.xref_get_key(cur, "Parent")[0] == "xref"
        if subtype == "/Widget" and parent and not named:
            continue
        kids = get_value(doc, cur, "Kids")
        if isinstance(kids, ArrayObject):
            for kid in kids:
                if not isinstance(kid, IndirectObject):
                    raise ValueError("El campo contiene un descendiente PDF no representable.")
                if (doc.xref_get_key(kid.idnum, "Subtype")[1] != "/Widget"
                        or doc.xref_get_key(kid.idnum, "T")[0] != "null"):
                    return None  # grupo no terminal, con campos hijos independientes
        if named or typed or isinstance(kids, ArrayObject) or subtype == "/Widget":
            return cur
    return None


def terminal_field_nodes(doc, xref: int) -> list[int]:
    """Campo terminal y sus widgets, sin padres de agrupación ni campos hermanos."""
    owner = terminal_field_owner(doc, xref)
    if owner is None:
        return []
    nodes = [owner]
    kids = get_value(doc, owner, "Kids")
    if isinstance(kids, ArrayObject):
        for kid in kids:
            if not isinstance(kid, IndirectObject):
                raise ValueError("Widget PDF no representable.")
            if kid.idnum not in nodes:
                nodes.append(kid.idnum)
    if xref not in nodes:
        nodes.append(xref)
    return nodes


def reachable_xrefs(doc, *, excluded: set[int] | None = None) -> set[int]:
    """Objetos todavía usados por el catálogo, sin entrar en nodos eliminados.

    Seguir referencias estructurales evita tratar texto parecido a '12 0 R'
    como un enlace y permite preservar recursos compartidos al censurar.
    """
    excluded = excluded or set()
    pending = [IndirectObject(doc.pdf_catalog(), 0, _CONTEXT)]
    visited: set[int] = set()
    steps = 0
    while pending:
        obj = pending.pop()
        steps += 1
        if steps > MAX_TRAVERSAL_NODES * 10:
            raise PdfObjectLimitError("El documento supera el límite de inspección de referencias.")
        if isinstance(obj, IndirectObject):
            if obj.idnum in excluded or obj.idnum in visited:
                continue
            if len(visited) >= MAX_TRAVERSAL_NODES:
                raise PdfObjectLimitError("El documento supera el límite de referencias inspeccionables.")
            visited.add(obj.idnum)
            pending.append(parse_object(doc.xref_object(obj.idnum)))
        elif isinstance(obj, DictionaryObject):
            pending.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            pending.extend(obj)
    return visited


def appearance_streams(doc, xref: int) -> list[int]:
    """Streams N/R/D y todos sus estados, conservando las referencias originales."""
    pending = []
    for key in ("AP/N", "AP/R", "AP/D"):
        kind, raw = doc.xref_get_key(xref, key)
        if kind != "null":
            pending.append(parse_object(raw))
    visited: set[int] = set()
    result = []
    steps = 0
    while pending:
        steps += 1
        if steps > MAX_TRAVERSAL_NODES:
            raise PdfObjectLimitError("Demasiados estados de apariencia para inspeccionar.")
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            if obj.idnum in visited:
                continue
            visited.add(obj.idnum)
            if doc.xref_is_stream(obj.idnum):
                result.append(obj.idnum)
            else:
                pending.append(parse_object(doc.xref_object(obj.idnum)))
        elif isinstance(obj, DictionaryObject):
            pending.extend(obj.values())
        else:
            raise ValueError("La apariencia PDF no es un stream o diccionario de estados válido.")
    return result


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

