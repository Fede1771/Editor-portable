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
_DANGEROUS_ACTION_TOKENS = (
    "/JavaScript", "/JS", "/Launch", "/ImportData", "/SubmitForm",
    "/RichMediaExecute", "/GoToR", "/GoToE", "/Sound", "/Movie", "/Rendition",
)
_XREF_RE = re.compile(r"(\d+)\s+0\s+R")


def _resolve_action_tree(doc: fitz.Document, raw_val: str, visited: set[int] | None = None) -> str:
    """Expande recursivamente un valor o referencia de acción PDF (incluyendo /Next) evitando ciclos."""
    if visited is None:
        visited = set()
    if not raw_val or raw_val == "null":
        return ""
    parts = [raw_val]
    for m in _XREF_RE.finditer(raw_val):
        xref = int(m.group(1))
        if xref <= 0 or xref in visited:
            continue
        visited.add(xref)
        try:
            obj_str = doc.xref_object(xref) or ""
        except Exception:
            obj_str = ""
        if obj_str:
            parts.append(obj_str)
            parts.append(_resolve_action_tree(doc, obj_str, visited))
    return "\n".join(parts)


def _iter_page_annot_xrefs(doc: fitz.Document, page: fitz.Page) -> list[int]:
    """Obtiene todos los xrefs de anotaciones y widgets de una página sin duplicados."""
    xrefs: list[int] = []
    seen: set[int] = set()
    try:
        for a in page.annots():
            if a.xref not in seen:
                seen.add(a.xref)
                xrefs.append(a.xref)
    except Exception:
        pass
    try:
        for w in page.widgets():
            if w.xref not in seen:
                seen.add(w.xref)
                xrefs.append(w.xref)
    except Exception:
        pass
    try:
        kind, val = doc.xref_get_key(page.xref, "Annots")
        if kind != "null":
            expanded = _resolve_action_tree(doc, val)
            for m in _XREF_RE.finditer(val + "\n" + expanded):
                x = int(m.group(1))
                if x > 0 and x not in seen:
                    seen.add(x)
                    xrefs.append(x)
    except Exception:
        pass
    return xrefs


def scan_document_security(doc: fitz.Document) -> dict:
    """Escanea el documento (catálogo, páginas, anotaciones, widgets y adjuntos) en busca de scripts y acciones."""
    threat_details: list[str] = []
    has_js = False
    has_launch = False
    has_open_action = False

    def _add_detail(msg: str) -> None:
        if msg not in threat_details:
            threat_details.append(msg)

    cat_xref = doc.pdf_catalog()
    if cat_xref > 0:
        keys = doc.xref_get_keys(cat_xref)

        # 1. /OpenAction en catálogo
        if "OpenAction" in keys:
            val = doc.xref_get_key(cat_xref, "OpenAction")[1]
            if val != "null":
                has_open_action = True
                expanded = _resolve_action_tree(doc, val)
                if "/Launch" in expanded:
                    has_launch = True
                    _add_detail("Acción automática de ejecución externa (/Launch)")
                elif "/JavaScript" in expanded or "/JS" in expanded:
                    has_js = True
                    _add_detail("Script automático de inicio (/JavaScript)")
                else:
                    _add_detail("Acción automática de apertura (/OpenAction)")

        # 2. /AA en catálogo
        if "AA" in keys:
            val = doc.xref_get_key(cat_xref, "AA")[1]
            if val != "null":
                expanded = _resolve_action_tree(doc, val)
                if "/JavaScript" in expanded or "/JS" in expanded:
                    has_js = True
                if "/Launch" in expanded:
                    has_launch = True
                _add_detail("Disparadores de eventos automáticos en catálogo (/AA)")

        # 3. /Names -> JavaScript (directo o indirecto)
        if "Names" in keys:
            names_kind, names_val = doc.xref_get_key(cat_xref, "Names")
            if names_kind != "null":
                js_kind, js_val = doc.xref_get_key(cat_xref, "Names/JavaScript")
                expanded = _resolve_action_tree(doc, names_val)
                if (js_kind != "null" and js_val != "null") or "/JavaScript" in expanded or "/JS" in expanded:
                    has_js = True
                    _add_detail("Scripts interactivos embebidos (Names/JavaScript)")

    # 4. Páginas, anotaciones y widgets (/AA y cadenas /A -> /Next)
    for pno in range(doc.page_count):
        page = doc[pno]
        p_keys = doc.xref_get_keys(page.xref)
        if "AA" in p_keys and doc.xref_get_key(page.xref, "AA")[1] != "null":
            expanded = _resolve_action_tree(doc, doc.xref_get_key(page.xref, "AA")[1])
            if "/JavaScript" in expanded or "/JS" in expanded:
                has_js = True
            if "/Launch" in expanded:
                has_launch = True
            _add_detail(f"Acción automática en página {pno + 1} (/AA)")

        for axref in _iter_page_annot_xrefs(doc, page):
            try:
                akeys = doc.xref_get_keys(axref)
            except Exception:
                continue
            if "AA" in akeys and doc.xref_get_key(axref, "AA")[1] != "null":
                expanded = _resolve_action_tree(doc, doc.xref_get_key(axref, "AA")[1])
                if "/JavaScript" in expanded or "/JS" in expanded:
                    has_js = True
                if "/Launch" in expanded:
                    has_launch = True
                _add_detail(f"Disparador automático en anotación/campo de página {pno + 1} (/AA)")

            if "A" in akeys and doc.xref_get_key(axref, "A")[1] != "null":
                expanded = _resolve_action_tree(doc, doc.xref_get_key(axref, "A")[1])
                if "/JavaScript" in expanded or "/JS" in expanded:
                    has_js = True
                    _add_detail(f"Acción de script en anotación/campo de página {pno + 1} (/JavaScript)")
                if "/Launch" in expanded:
                    has_launch = True
                    _add_detail(f"Acción de lanzamiento externo en página {pno + 1} (/Launch)")
                for tok in ("/ImportData", "/SubmitForm", "/RichMediaExecute", "/GoToR", "/GoToE"):
                    if tok in expanded:
                        _add_detail(f"Acción activa ({tok}) en página {pno + 1}")

    # 5. Adjuntos ejecutables o activos (usando extensión canónica normalizada - H40)
    from .attachments import canonical_extension, get_all_attachments, DANGEROUS_EXTENSIONS as _ATT_DANGEROUS
    dangerous_files = []
    for att in get_all_attachments(doc):
        fn = att.get("filename") or att.get("name") or ""
        ext = canonical_extension(fn)
        if ext in DANGEROUS_EXTENSIONS or ext in _ATT_DANGEROUS:
            dangerous_files.append(fn)
    if dangerous_files:
        _add_detail(f"Adjuntos potencialmente peligrosos: {', '.join(dangerous_files)}")

    return {
        "has_threats": len(threat_details) > 0,
        "has_js": has_js,
        "has_launch": has_launch,
        "has_open_action": has_open_action,
        "threat_details": threat_details,
    }


def _clean_action_on_xref(doc: fitz.Document, xref: int) -> int:
    """Limpia acciones peligrosas (/AA y /A o su cadena /Next) en una anotación o widget."""
    cleaned = 0
    try:
        akeys = doc.xref_get_keys(xref)
    except Exception:
        return 0

    if "AA" in akeys and doc.xref_get_key(xref, "AA")[1] != "null":
        doc.xref_set_key(xref, "AA", "null")
        cleaned += 1

    if "A" in akeys:
        a_kind, a_val = doc.xref_get_key(xref, "A")
        if a_val != "null":
            expanded = _resolve_action_tree(doc, a_val)
            if any(tok in expanded for tok in _DANGEROUS_ACTION_TOKENS):
                # Si la acción raíz es un enlace URI simple pero encadena /Next peligroso, conservar solo el URI
                if "/S /URI" in a_val and not any(tok in a_val.split("/Next")[0] for tok in _DANGEROUS_ACTION_TOKENS):
                    doc.xref_set_key(xref, "A/Next", "null")
                else:
                    doc.xref_set_key(xref, "A", "null")
                cleaned += 1
    return cleaned


def sanitize_document(doc: fitz.Document) -> int:
    """Elimina permanentemente scripts, acciones automáticas y llamadas a ejecutables (H10)."""
    cleaned = 0
    cat_xref = doc.pdf_catalog()
    if cat_xref > 0:
        keys = doc.xref_get_keys(cat_xref)
        if "OpenAction" in keys and doc.xref_get_key(cat_xref, "OpenAction")[1] != "null":
            doc.xref_set_key(cat_xref, "OpenAction", "null")
            cleaned += 1
        if "AA" in keys and doc.xref_get_key(cat_xref, "AA")[1] != "null":
            doc.xref_set_key(cat_xref, "AA", "null")
            cleaned += 1
        if "Names" in keys:
            names_kind, names_val = doc.xref_get_key(cat_xref, "Names")
            if names_val != "null":
                js_kind, js_val = doc.xref_get_key(cat_xref, "Names/JavaScript")
                if js_kind != "null" and js_val != "null":
                    doc.xref_set_key(cat_xref, "Names/JavaScript", "null")
                    cleaned += 1
                if names_kind == "xref":
                    try:
                        nxref = int(names_val.split()[0])
                        if "JavaScript" in doc.xref_get_keys(nxref):
                            doc.xref_set_key(nxref, "JavaScript", "null")
                            cleaned += 1
                    except Exception:
                        pass
                # Si todavía persiste /JavaScript en Names, anular Names/JavaScript o Names
                expanded_after = _resolve_action_tree(doc, doc.xref_get_key(cat_xref, "Names")[1])
                if "/JavaScript" in expanded_after or "/JS" in expanded_after:
                    doc.xref_set_key(cat_xref, "Names", "null")
                    cleaned += 1

    # Limpiar eventos y acciones en páginas, anotaciones y widgets
    for page in doc:
        p_keys = doc.xref_get_keys(page.xref)
        if "AA" in p_keys and doc.xref_get_key(page.xref, "AA")[1] != "null":
            doc.xref_set_key(page.xref, "AA", "null")
            cleaned += 1
        for axref in _iter_page_annot_xrefs(doc, page):
            cleaned += _clean_action_on_xref(doc, axref)

    return cleaned


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


def create_sanitized_copy(doc: fitz.Document, out_path: str) -> None:
    """Genera una copia anónima y sanitizada preservando la estructura documental (marcadores y adjuntos, H19)."""
    raw = doc.tobytes()
    copy_doc = fitz.open("pdf", raw)
    try:
        sanitize_metadata(copy_doc)
        sanitize_document(copy_doc)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        copy_doc.save(out_path, deflate=True, garbage=4)
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
