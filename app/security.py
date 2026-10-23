"""Módulo de seguridad: escaneo pasivo de amenazas, sanitización y protección anti-phishing."""
from __future__ import annotations

import html
import ipaddress
import os
import re
from urllib.parse import unquote, urlparse

import pymupdf as fitz
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout,
)

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".ps1", ".psm1", ".scr", ".pif", ".com", ".jar", ".reg", ".msi", ".dll",
    ".hta", ".cpl", ".lnk", ".iso", ".chm", ".url", ".docm", ".xlsm", ".pptm",
    ".dotm", ".xltm", ".potm", ".wsc", ".inf", ".scf",
    ".msp", ".mst", ".appx", ".msix", ".appref-ms", ".settingcontent-ms", ".library-ms",
    ".img", ".vhd", ".vhdx", ".application", ".gadget", ".msc", ".ps1xml", ".psc1",
    ".psd1", ".sys", ".drv", ".ocx", ".xll", ".xlam", ".ppam", ".sldm", ".xlsb",
    ".one", ".website", ".vb", ".shb", ".shs", ".ws", ".sct", ".py", ".pyw",
}

ALLOWED_BROWSER_SCHEMES = {"http", "https"}
_DANGEROUS_ACTIONS = {
    "/JavaScript", "/Launch", "/ImportData", "/SubmitForm", "/RichMediaExecute",
    "/GoToR", "/GoToE", "/Sound", "/Movie", "/Rendition",
}


class UnsupportedActiveContentError(ValueError):
    pass


def has_xfa(doc: fitz.Document) -> bool:
    return doc.xref_get_key(doc.pdf_catalog(), "AcroForm/XFA")[0] != "null"


def _action_types(doc, value) -> set[str]:
    """Sólo diccionarios de acción, eventos y /Next; no strings ni backlinks /P."""
    from .pdf_objects import ArrayObject, DictionaryObject, IndirectObject, NameObject, resolve
    pending = [value]
    visited = set()
    types = set()
    count = 0
    while pending:
        count += 1
        if count > 10000:
            raise ValueError("El árbol de acciones supera el límite de inspección.")
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            if obj.idnum in visited:
                continue
            visited.add(obj.idnum)
        obj = resolve(doc, obj)
        if isinstance(obj, ArrayObject):
            pending.extend(obj)
        elif isinstance(obj, DictionaryObject):
            kind = obj.get("/S")
            if isinstance(kind, NameObject):
                types.add(str(kind))
                if obj.get("/Next") is not None:
                    pending.append(obj.get("/Next"))
            else:
                # /AA es un diccionario de eventos; nunca interpretar su texto.
                pending.extend(v for v in obj.values() if isinstance(v, (DictionaryObject, ArrayObject, IndirectObject)))
    return types


def _iter_page_annot_xrefs(doc, page) -> list[int]:
    from .pdf_objects import get_value, ArrayObject, IndirectObject, field_chain
    result = set()
    values = get_value(doc, page.xref, "Annots")
    if isinstance(values, ArrayObject):
        for value in values:
            if isinstance(value, IndirectObject):
                result.update(field_chain(doc, value.idnum))
    return sorted(result)


def _action_locations(doc):
    """Ubicaciones reales de acciones, compartidas por escáner y limpiador."""
    from .pdf_objects import get_value
    cat = doc.pdf_catalog()
    for key in ("OpenAction", "AA"):
        value = get_value(doc, cat, key)
        if value is not None:
            yield cat, key, value, "catálogo"
    for pno, page in enumerate(doc):
        value = get_value(doc, page.xref, "AA")
        if value is not None:
            yield page.xref, "AA", value, f"página {pno + 1}"
        for xref in _iter_page_annot_xrefs(doc, page):
            for key in ("A", "AA"):
                value = get_value(doc, xref, key)
                if value is not None:
                    yield xref, key, value, f"anotación/campo de página {pno + 1}"


def scan_document_security(doc: fitz.Document) -> dict:
    from .attachments import canonical_extension, get_all_attachments
    details = []
    has_js = has_launch = has_open_action = False
    incomplete = False
    xfa = has_xfa(doc)
    if xfa:
        details.append("Formulario XFA no inspeccionable: puede contener scripts y datos alternativos")
    try:
        cat = doc.pdf_catalog()
        if doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
            has_js = True
            details.append("Scripts interactivos embebidos (Names/JavaScript)")
        for xref, key, value, label in _action_locations(doc):
            types = _action_types(doc, value)
            has_js |= "/JavaScript" in types
            has_launch |= "/Launch" in types
            has_open_action |= key == "OpenAction"
            active = types & _DANGEROUS_ACTIONS
            if key in {"AA", "OpenAction"} or active:
                details.append(f"Acción en {label} ({key}: {', '.join(sorted(types)) or 'automática'})")
    except Exception as exc:
        incomplete = True
        details.append(f"Inspección de acciones incompleta: {exc}")
    dangerous = [a.get("filename") or a.get("name") or "" for a in get_all_attachments(doc)
                 if canonical_extension(a.get("filename") or a.get("name") or "") in DANGEROUS_EXTENSIONS]
    if dangerous:
        details.append("Adjuntos potencialmente peligrosos: " + ", ".join(dangerous))
    return {"has_threats": bool(details), "has_js": has_js, "has_launch": has_launch,
            "has_open_action": has_open_action, "has_xfa": xfa, "incomplete": incomplete,
            "threat_details": list(dict.fromkeys(details))}


def sanitize_document(doc: fitz.Document, *, remove_xfa: bool = False) -> int:
    """Limpiar claves de acción; XFA sólo con consentimiento explícito de pérdida."""
    from .pdf_objects import DictionaryObject, NameObject
    xfa = has_xfa(doc)
    if xfa and not remove_xfa:
        raise UnsupportedActiveContentError(
            "El PDF contiene XFA. No se puede garantizar su saneamiento sin eliminar ese formulario."
        )
    # Inspeccionar todo antes de comenzar: un error no debe producir limpieza parcial.
    locations = list(_action_locations(doc))
    changes = []
    for xref, key, value, label in locations:
        kinds = _action_types(doc, value)
        if key in {"AA", "OpenAction"} or kinds & _DANGEROUS_ACTIONS:
            root_kind = value.get("/S") if isinstance(value, DictionaryObject) else None
            # Conservar URI simple y quitar únicamente su continuación activa.
            if key == "A" and isinstance(root_kind, NameObject) and root_kind == "/URI":
                changes.append((xref, "A/Next"))
            else:
                changes.append((xref, key))
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
        changes.append((cat, "Names/JavaScript"))
    if xfa:
        changes.append((cat, "AcroForm/XFA"))
    for xref, key in changes:
        doc.xref_set_key(xref, key, "null")
    return len(changes)


def sanitize_metadata(doc: fitz.Document) -> None:
    """Despoja al documento de nombres de usuario, rutas de disco, software de autoría, rastros XMP y autores de anotaciones."""
    doc.set_metadata({
        "title": "",
        "author": "",
        "subject": "",
        "keywords": "",
        "creator": "Editor PDF Portable",
        "producer": "Editor PDF Portable",
        "creationDate": "",
        "modDate": "",
    })
    try:
        doc.del_xml_metadata()
    except Exception:
        pass

    # Anonimizar metadatos de autor y fechas en todas las anotaciones existentes (H11)
    try:
        for page in doc:
            for annot in page.annots():
                info = dict(annot.info or {})
                changed = False
                if info.get("title"):
                    info["title"] = "Usuario"
                    changed = True
                if info.get("creationDate"):
                    info["creationDate"] = ""
                    changed = True
                if info.get("modDate"):
                    info["modDate"] = ""
                    changed = True
                if changed:
                    annot.set_info(info)
    except Exception:
        pass


def create_sanitized_copy(doc: fitz.Document, out_path: str, *, remove_xfa: bool = False) -> None:
    """Genera una copia anónima y sanitizada preservando la estructura documental (marcadores y adjuntos, H19)."""
    from .document_io import clone_pdf, save_pdf
    copy_doc = clone_pdf(doc)
    try:
        sanitize_metadata(copy_doc)
        sanitize_document(copy_doc, remove_xfa=remove_xfa)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        save_pdf(copy_doc, out_path, deflate=True, garbage=4)
    finally:
        copy_doc.close()


def _is_ip_literal(host: str) -> bool:
    if not host:
        return False
    candidate = host.strip("[]")
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        pass
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", candidate))


def check_url_safety(url: str, visible_text: str = "") -> dict:
    """Evalúa estructura, esquema y señales heurísticas de un enlace (H42, H43).

    Nota: la ausencia de señales locales (`warnings == []`) significa `'no_signals_detected'`,
    nunca una garantía criptográfica ni de reputación del destino remoto.
    """
    raw = (url or "").strip()
    warnings: list[str] = []
    has_ctrl = bool(re.search(r"[\x00-\x1f\x7f]", raw))
    if has_ctrl:
        warnings.append("El enlace contiene caracteres de control no imprimibles.")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    can_open = True
    if scheme not in ALLOWED_BROWSER_SCHEMES:
        can_open = False
        warnings.append(
            f"Protocolo bloqueado para apertura en navegador ('{scheme or 'sin esquema'}:'). "
            "Solo se permiten enlaces web http:// y https://."
        )

    if scheme in ALLOWED_BROWSER_SCHEMES and not host:
        can_open = False
        warnings.append("El enlace no contiene un dominio o host de destino válido.")

    if has_ctrl:
        can_open = False

    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        warnings.append("El enlace incluye credenciales o prefijo 'usuario@host' que puede ocultar el destino real.")

    if host and _is_ip_literal(host):
        warnings.append(f"El enlace apunta directamente a una dirección IP literal ({host}) en lugar de un nombre de dominio.")

    if host and ("xn--" in host or any(ord(ch) > 127 for ch in host)):
        warnings.append(f"El dominio ({host}) utiliza codificación internacional (IDN/Punycode); verificá posibles homógrafos.")

    from .attachments import canonical_extension
    decoded_path = unquote(parsed.path or "")
    last_segment = os.path.basename(decoded_path.rstrip("/"))
    ext = canonical_extension(last_segment) if last_segment else ""
    if ext in DANGEROUS_EXTENSIONS or any(decoded_path.lower().rstrip(" .").endswith(e) for e in DANGEROUS_EXTENSIONS):
        warnings.append("El enlace apunta a la descarga directa de un programa o archivo activo/ejecutable.")

    text_clean = unquote((visible_text or "").strip()).lower()
    if "." in text_clean and " " not in text_clean and "<" not in text_clean:
        text_parsed = urlparse("https://" + text_clean if not text_clean.startswith(("http://", "https://")) else text_clean)
        text_host = (text_parsed.hostname or "").lower()
        if text_host and host and text_host != host and not host.endswith("." + text_host):
            warnings.append(f"El texto visible aparenta ser '{text_clean}', pero el destino real es '{host}'.")

    is_safe = bool(can_open and len(warnings) == 0)
    return {
        "is_safe": is_safe,
        "can_open": can_open,
        "status": "no_signals_detected" if is_safe else ("blocked" if not can_open else "suspicious"),
        "url": raw,
        "scheme": scheme,
        "host": host,
        "warnings": warnings,
    }


def _visible_literal(text: str) -> str:
    """Representa caracteres de control de forma visible sin interpretar HTML (H44)."""
    return re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\x{ord(m.group(0)):02x}", text or "")


class SecurityBanner(QFrame):
    """Barra superior discreta que alerta si el documento contiene scripts o acciones automáticas."""

    sanitizeRequested = Signal()

    _WARN_STYLE = """
        QFrame {
            background-color: #fff3cd;
            border-bottom: 1px solid #ffeeba;
            padding: 4px 12px;
        }
        QLabel {
            color: #856404;
            font-size: 9pt;
        }
        QPushButton#btn_sanitize {
            background-color: #d39e00;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 4px 10px;
            font-weight: bold;
            font-size: 8.5pt;
        }
        QPushButton#btn_sanitize:hover {
            background-color: #ba8b00;
        }
        QPushButton#btn_close {
            background: transparent;
            border: none;
            color: #856404;
            font-size: 11pt;
            font-weight: bold;
        }
        QPushButton#btn_close:hover {
            color: #533f03;
        }
    """

    _CLEAN_STYLE = """
        QFrame {
            background-color: #d4edda;
            border-bottom: 1px solid #c3e6cb;
            padding: 4px 12px;
        }
        QLabel {
            color: #155724;
            font-size: 9pt;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self._WARN_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.icon_lbl = QLabel("🛡️")
        self.icon_lbl.setStyleSheet("font-size: 12pt;")
        layout.addWidget(self.icon_lbl)

        self.msg_lbl = QLabel("")
        self.msg_lbl.setTextFormat(Qt.RichText)
        self.msg_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.msg_lbl)

        self.btn_sanitize = QPushButton("Desactivar y Limpiar Scripts")
        self.btn_sanitize.setObjectName("btn_sanitize")
        self.btn_sanitize.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_sanitize.clicked.connect(self.sanitizeRequested.emit)
        layout.addWidget(self.btn_sanitize)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_close")
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

        self.hide()

    def show_threats(self, sec_info: dict):
        details = sec_info.get("threat_details", [])
        if not details:
            self.hide()
            return
        # N03/H44: restaurar siempre estilo de advertencia, icono, botón y escapar entradas no confiables
        self.setStyleSheet(self._WARN_STYLE)
        self.icon_lbl.setText("🛡️")
        self.btn_sanitize.show()
        escaped_summary = " • ".join(html.escape(_visible_literal(str(d))) for d in details)
        self.msg_lbl.setText(
            f"<b>Aviso de seguridad:</b> {escaped_summary}. "
            "<i>(No se ejecutan scripts dentro del visor)</i>"
        )
        self.show()

    def show_cleaned(self):
        self.setStyleSheet(self._CLEAN_STYLE)
        self.icon_lbl.setText("✓")
        self.msg_lbl.setText("<b>Documento sanitizado con éxito:</b> Los scripts y acciones automáticas detectados fueron removidos.")
        self.btn_sanitize.hide()
        self.show()


class SafeLinkDialog(QDialog):
    """Diálogo de protección anti-phishing al hacer clic en un enlace externo."""

    def __init__(self, url: str, text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar enlace externo")
        self.resize(500, 240)
        self.url = url
        self.safety = check_url_safety(url, text)
        self.warning_labels: list[QLabel] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        header_lbl = QLabel("Destino del enlace seleccionado en el documento:")
        header_lbl.setTextFormat(Qt.PlainText)
        header_lbl.setStyleSheet("font-size: 10pt; font-weight: bold;")
        layout.addWidget(header_lbl)

        # Tarjeta con la URL (H44: PlainText estricto)
        url_frame = QFrame()
        url_frame.setStyleSheet("""
            QFrame {
                background-color: #f1f3f4;
                border: 1px solid #dadce0;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QLabel {
                font-family: Consolas, monospace;
                font-size: 9.5pt;
                color: #1a73e8;
            }
        """)
        uf_layout = QVBoxLayout(url_frame)
        uf_layout.setContentsMargins(4, 4, 4, 4)
        self.lbl_dest = QLabel(_visible_literal(url))
        self.lbl_dest.setTextFormat(Qt.PlainText)
        self.lbl_dest.setWordWrap(True)
        self.lbl_dest.setTextInteractionFlags(Qt.TextSelectableByMouse)
        uf_layout.addWidget(self.lbl_dest)
        layout.addWidget(url_frame)

        # Advertencias si no es seguro o nota de alcance heurístico (H43, H44)
        if not self.safety["is_safe"]:
            warn_frame = QFrame()
            warn_frame.setStyleSheet("""
                QFrame {
                    background-color: #fde8e8;
                    border: 1px solid #f8b4b4;
                    border-radius: 6px;
                    padding: 8px;
                }
                QLabel {
                    color: #9b1c1c;
                    font-size: 9pt;
                }
            """)
            wf_layout = QVBoxLayout(warn_frame)
            wf_layout.setContentsMargins(4, 4, 4, 4)
            for w in self.safety["warnings"]:
                w_lbl = QLabel(f"⚠️ {_visible_literal(w)}")
                w_lbl.setTextFormat(Qt.PlainText)
                w_lbl.setWordWrap(True)
                wf_layout.addWidget(w_lbl)
                self.warning_labels.append(w_lbl)
            layout.addWidget(warn_frame)
        else:
            note_lbl = QLabel("ℹ️ Sin señales sospechosas locales. Verificá que reconozcas el dominio antes de abrir.")
            note_lbl.setTextFormat(Qt.PlainText)
            note_lbl.setWordWrap(True)
            note_lbl.setStyleSheet("color: #5f6368; font-size: 8.5pt;")
            layout.addWidget(note_lbl)

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_copy = QPushButton("Copiar enlace")
        btn_copy.setCursor(QCursor(Qt.PointingHandCursor))
        btn_copy.clicked.connect(self._copy_url)
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_open = QPushButton("Abrir en navegador")
        self.btn_open.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_open.setEnabled(bool(self.safety["can_open"]))
        if not self.safety["can_open"]:
            self.btn_open.setStyleSheet("background-color: #9e9e9e; color: #f5f5f5; padding: 6px 14px;")
        elif not self.safety["is_safe"]:
            self.btn_open.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 6px 14px;")
        else:
            self.btn_open.setStyleSheet("background-color: #1a73e8; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_open.clicked.connect(self._open_url)
        btn_layout.addWidget(self.btn_open)

        layout.addLayout(btn_layout)

    def _copy_url(self):
        QApplication.clipboard().setText(self.url)
        self.accept()

    def _open_url(self):
        # H42: revalidación estricta de esquema y host antes de despachar a QDesktopServices
        recheck = check_url_safety(self.url)
        if not recheck["can_open"]:
            return
        qurl = QUrl(self.url.strip(), QUrl.StrictMode)
        if not qurl.isValid() or qurl.scheme().lower() not in ALLOWED_BROWSER_SCHEMES or not qurl.host():
            return
        QDesktopServices.openUrl(qurl)
        self.accept()
