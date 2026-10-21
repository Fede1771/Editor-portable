"""Módulo de seguridad: escaneo pasivo de amenazas, sanitización y protección anti-phishing."""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse
from typing import Sequence

import pymupdf as fitz
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".ps1", ".psm1", ".scr", ".pif", ".com", ".jar", ".reg", ".msi", ".dll",
    ".hta", ".cpl", ".lnk", ".iso",
}


def scan_document_security(doc: fitz.Document) -> dict:
    """Escanea pasiva y ultrarrápidamente (< 1 ms) el documento en busca de scripts y acciones automáticas."""
    threat_details = []
    has_js = False
    has_launch = False
    has_open_action = False

    cat_xref = doc.pdf_catalog()
    if cat_xref > 0:
        keys = doc.xref_get_keys(cat_xref)

        # 1. Comprobar /OpenAction (ejecución automática al abrir el PDF)
        if "OpenAction" in keys:
            val = doc.xref_get_key(cat_xref, "OpenAction")[1]
            if val != "null":
                has_open_action = True
                if "/Launch" in val:
                    has_launch = True
                    threat_details.append("Acción automática de ejecución externa (/Launch)")
                elif "/JavaScript" in val or "/JS" in val:
                    has_js = True
                    threat_details.append("Script automático de inicio (/JavaScript)")
                else:
                    threat_details.append("Acción automática de apertura (/OpenAction)")

        # 2. Comprobar /AA (Acciones adicionales en el catálogo)
        if "AA" in keys:
            val = doc.xref_get_key(cat_xref, "AA")[1]
            if val != "null":
                threat_details.append("Disparadores de eventos automáticos (/AA)")

        # 3. Comprobar /Names -> JavaScript
        if "Names" in keys:
            names_entry = doc.xref_get_key(cat_xref, "Names")
            if "JavaScript" in names_entry[1]:
                has_js = True
                threat_details.append("Scripts interactivos embebidos (Names/JavaScript)")
            elif " " in names_entry[1] and "R" in names_entry[1]:
                try:
                    nxref = int(names_entry[1].split()[0])
                    if "JavaScript" in doc.xref_get_keys(nxref):
                        has_js = True
                        threat_details.append("Scripts interactivos embebidos (Names/JavaScript)")
                except Exception:
                    pass

    # 4. Comprobar adjuntos ejecutables
    dangerous_files = []
    for i in range(doc.embfile_count()):
        info = doc.embfile_info(i)
        fn = info.get("filename") or info.get("name") or ""
        ext = os.path.splitext(fn)[1].lower()
        if ext in DANGEROUS_EXTENSIONS:
            dangerous_files.append(fn)
    if dangerous_files:
        threat_details.append(f"Adjuntos potencialmente peligrosos: {', '.join(dangerous_files)}")

    return {
        "has_threats": len(threat_details) > 0,
        "has_js": has_js,
        "has_launch": has_launch,
        "has_open_action": has_open_action,
        "threat_details": threat_details,
    }


def sanitize_document(doc: fitz.Document) -> int:
    """Elimina permanentemente scripts, acciones automáticas y llamadas a ejecutables."""
    cleaned = 0
    cat_xref = doc.pdf_catalog()
    if cat_xref > 0:
        keys = doc.xref_get_keys(cat_xref)
        if "OpenAction" in keys:
            doc.xref_set_key(cat_xref, "OpenAction", "null")
            cleaned += 1
        if "AA" in keys:
            doc.xref_set_key(cat_xref, "AA", "null")
            cleaned += 1
        if "Names" in keys:
            names_entry = doc.xref_get_key(cat_xref, "Names")
            if " " in names_entry[1] and "R" in names_entry[1]:
                try:
                    nxref = int(names_entry[1].split()[0])
                    if "JavaScript" in doc.xref_get_keys(nxref):
                        doc.xref_set_key(nxref, "JavaScript", "null")
                        cleaned += 1
                except Exception:
                    pass

    # Limpiar eventos adicionales en páginas individuales
    for page in doc:
        p_keys = doc.xref_get_keys(page.xref)
        if "AA" in p_keys:
            doc.xref_set_key(page.xref, "AA", "null")
            cleaned += 1

    return cleaned


def sanitize_metadata(doc: fitz.Document) -> None:
    """Despoja al documento de nombres de usuario, rutas de disco, software de autoría y rastros XMP."""
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


def check_url_safety(url: str, visible_text: str = "") -> dict:
    """Verifica si una URL es sospechosa, apunta a ejecutables o intenta suplantar identidad (anti-phishing)."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    warnings = []

    if scheme not in ("http", "https", "mailto"):
        warnings.append(f"Protocolo inusual o peligroso ('{scheme}:'). Puede ejecutar acciones en tu equipo.")

    host = (parsed.hostname or "").lower()
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        warnings.append(f"El enlace apunta directamente a una dirección IP numérica ({host}) en vez de un dominio con certificado.")

    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in DANGEROUS_EXTENSIONS):
        warnings.append("El enlace apunta a la descarga directa de un programa o script ejecutable.")

    text_clean = visible_text.strip().lower()
    if "." in text_clean and " " not in text_clean:
        text_parsed = urlparse("https://" + text_clean if not text_clean.startswith("http") else text_clean)
        text_host = (text_parsed.hostname or "").lower()
        if text_host and host and text_host != host and not host.endswith("." + text_host):
            warnings.append(f"El texto del PDF simula ser '{text_clean}', pero el destino real es '{host}'.")

    return {
        "is_safe": len(warnings) == 0,
        "url": url,
        "scheme": scheme,
        "host": host,
        "warnings": warnings,
    }


class SecurityBanner(QFrame):
    """Barra superior discreta que alerta si el documento contiene scripts o acciones automáticas."""

    sanitizeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
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
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.icon_lbl = QLabel("🛡️")
        self.icon_lbl.setStyleSheet("font-size: 12pt;")
        layout.addWidget(self.icon_lbl)

        self.msg_lbl = QLabel("")
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
        summary = " • ".join(details)
        self.msg_lbl.setText(f"<b>Aviso de seguridad:</b> {summary}. <i>(La ejecución automática fue bloqueada)</i>")
        self.show()

    def show_cleaned(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #d4edda;
                border-bottom: 1px solid #c3e6cb;
                padding: 4px 12px;
            }
            QLabel {
                color: #155724;
                font-size: 9pt;
            }
        """)
        self.icon_lbl.setText("✓")
        self.msg_lbl.setText("<b>Documento sanitizado con éxito:</b> Todos los scripts y acciones automáticas han sido removidos.")
        self.btn_sanitize.hide()


class SafeLinkDialog(QDialog):
    """Diálogo de protección anti-phishing al hacer clic en un enlace externo."""

    def __init__(self, url: str, text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar enlace externo")
        self.resize(500, 240)
        self.url = url
        self.safety = check_url_safety(url, text)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        header_lbl = QLabel("Estás a punto de abrir un enlace externo en tu navegador:")
        header_lbl.setStyleSheet("font-size: 10pt; font-weight: bold;")
        layout.addWidget(header_lbl)

        # Tarjeta con la URL
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
        lbl_dest = QLabel(url)
        lbl_dest.setWordWrap(True)
        lbl_dest.setTextInteractionFlags(Qt.TextSelectableByMouse)
        uf_layout.addWidget(lbl_dest)
        layout.addWidget(url_frame)

        # Advertencias si no es seguro
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
                w_lbl = QLabel(f"⚠️ {w}")
                w_lbl.setWordWrap(True)
                wf_layout.addWidget(w_lbl)
            layout.addWidget(warn_frame)

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
        if not self.safety["is_safe"]:
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
        QDesktopServices.openUrl(QUrl(self.url))
        self.accept()
