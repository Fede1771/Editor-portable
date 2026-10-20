"""Gestión y visualización de archivos adjuntos embebidos en el PDF."""
from __future__ import annotations

import os
import tempfile
from typing import Callable

import pymupdf as fitz
from PySide6.QtCore import QFileInfo, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFileIconProvider, QHBoxLayout, QHeaderView,
    QMenu, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)


DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".ps1", ".psm1", ".scr", ".pif", ".com", ".jar", ".reg", ".msi", ".dll",
    ".hta", ".cpl", ".lnk", ".iso",
}


def format_size(size_bytes: int) -> str:
    """Retorna un tamaño formateado legible (B, KB, MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def parse_pdf_date(date_str: str) -> str:
    """Convierte fechas en formato PDF D:YYYYMMDDHHmmSS a formato estándar DD/MM/YYYY HH:mm."""
    if not date_str:
        return ""
    s = date_str.strip()
    if s.startswith("D:"):
        s = s[2:]
    if len(s) >= 14:
        yyyy = s[0:4]
        mm = s[4:6]
        dd = s[6:8]
        hh = s[8:10]
        minute = s[10:12]
        return f"{dd}/{mm}/{yyyy} {hh}:{minute}"
    if len(s) >= 8:
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
    return date_str


def get_all_attachments(doc: fitz.Document) -> list[dict]:
    """Recopila todos los archivos adjuntos tanto a nivel de documento como en anotaciones."""
    items: list[dict] = []
    # 1. Archivos incrustados a nivel de catálogo de documento
    for i in range(doc.embfile_count()):
        info = doc.embfile_info(i)
        fn = info.get("filename") or info.get("ufilename") or info.get("name") or f"adjunto_{i+1}"
        size = info.get("size") or info.get("length") or 0
        date_str = parse_pdf_date(info.get("modDate") or "")
        desc = info.get("description") or ""
        items.append({
            "source": "embedded",
            "index": i,
            "name": info.get("name") or fn,
            "filename": fn,
            "size": size,
            "date": date_str,
            "desc": desc,
        })

    # 2. Archivos adjuntos ubicados en anotaciones de página
    for pno, page in enumerate(doc):
        for annot in page.annots():
            if annot.type[1] == "FileAttachment":
                info = getattr(annot, "file_info", {}) or {}
                fn = info.get("filename") or info.get("ufilename") or f"adjunto_pag_{pno+1}"
                size = info.get("size") or 0
                items.append({
                    "source": "annot",
                    "page": pno,
                    "annot": annot,
                    "name": fn,
                    "filename": fn,
                    "size": size,
                    "date": "",
                    "desc": f"En página {pno + 1}",
                })

    return items


def get_attachment_bytes(doc: fitz.Document, item: dict) -> bytes:
    """Extrae los bytes crudos del archivo adjunto seleccionado."""
    if item.get("source") == "annot":
        annot = item.get("annot")
        if annot is not None and hasattr(annot, "get_file"):
            return annot.get_file() or b""
    idx = item.get("index", 0)
    return doc.embfile_get(idx)


class AttachmentWidget(QWidget):
    """Panel lateral interactivo para explorar, abrir, extraer y gestionar archivos adjuntos."""

    openPdfRequested = Signal(bytes, str)  # (pdf_bytes, filename)
    attachmentChanged = Signal()          # Cuando se agrega o elimina un adjunto

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.icon_provider = QFileIconProvider()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nombre", "Tamaño", "Fecha"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Barra de botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(2, 2, 2, 2)
        btn_layout.setSpacing(4)

        self.btn_open = QPushButton("Abrir")
        self.btn_open.setToolTip("Abrir el archivo adjunto seleccionado")
        self.btn_open.clicked.connect(self.open_selected)

        self.btn_save = QPushButton("Guardar…")
        self.btn_save.setToolTip("Guardar el archivo seleccionado en el disco")
        self.btn_save.clicked.connect(self.save_selected)

        self.btn_extract_all = QPushButton("Extraer todo…")
        self.btn_extract_all.setToolTip("Guardar todos los adjuntos en una carpeta")
        self.btn_extract_all.clicked.connect(self.extract_all)

        self.btn_add = QPushButton("Adjuntar…")
        self.btn_add.setToolTip("Incrustar un nuevo archivo dentro del PDF")
        self.btn_add.clicked.connect(self.add_attachment)

        self.btn_del = QPushButton("Eliminar")
        self.btn_del.setToolTip("Eliminar el archivo adjunto del PDF")
        self.btn_del.clicked.connect(self.delete_selected)

        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_extract_all)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_del)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)
        layout.addLayout(btn_layout)

        self.reload()

    def count(self) -> int:
        return self.tree.topLevelItemCount()

    def reload(self) -> int:
        """Recarga la lista de adjuntos desde el documento PDF."""
        self.tree.clear()
        attachments = get_all_attachments(self.doc)
        for att in attachments:
            fn = att["filename"]
            sz = format_size(att["size"])
            dt = att["date"]
            item = QTreeWidgetItem([fn, sz, dt])
            item.setData(0, Qt.UserRole, att)

            # Icono nativo de Windows para la extensión del archivo
            qfi = QFileInfo(fn)
            icon = self.icon_provider.icon(qfi)
            if not icon.isNull():
                item.setIcon(0, icon)

            tooltip = f"Archivo: {fn}\nTamaño: {sz}\nModificado: {dt}"
            if att.get("desc"):
                tooltip += f"\nDescripción: {att['desc']}"
            item.setToolTip(0, tooltip)
            self.tree.addTopLevelItem(item)

        has_items = len(attachments) > 0
        self.btn_open.setEnabled(has_items)
        self.btn_save.setEnabled(has_items)
        self.btn_extract_all.setEnabled(has_items)
        self.btn_del.setEnabled(has_items)
        return len(attachments)

    def _selected_item_data(self) -> dict | None:
        item = self.tree.currentItem()
        if item is not None:
            return item.data(0, Qt.UserRole)
        return None

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int):
        att = item.data(0, Qt.UserRole)
        if att:
            self._open_attachment(att)

    def open_selected(self):
        att = self._selected_item_data()
        if att:
            self._open_attachment(att)

    def _open_attachment(self, att: dict):
        fn = att["filename"]
        try:
            data = get_attachment_bytes(self.doc, att)
            if not data:
                QMessageBox.warning(self, "Archivo vacío", f"El archivo adjunto '{fn}' no contiene datos.")
                return

            ext = os.path.splitext(fn)[1].lower()
            if ext in DANGEROUS_EXTENSIONS:
                r = QMessageBox.warning(
                    self,
                    "Advertencia de seguridad",
                    f"El archivo adjunto «{fn}» tiene una extensión ejecutable o de script ({ext}).\n\n"
                    "Ejecutar este tipo de archivos directamente puede comprometer la seguridad de tu equipo "
                    "si el PDF proviene de un origen desconocido.\n\n"
                    "Por seguridad, el editor no lo ejecutará automáticamente.\n"
                    "¿Deseas guardarlo en una carpeta para analizarlo previamente con tu antivirus?",
                    QMessageBox.Save | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if r == QMessageBox.Save:
                    self.save_selected()
                return

            if ext == ".pdf":
                # Si es PDF, emitir señal para abrir en nueva pestaña del visor
                self.openPdfRequested.emit(data, fn)
                return

            # Para otros formatos (Excel, Word, imágenes, etc.), guardar en archivo temporal y abrir en Windows
            temp_dir = tempfile.mkdtemp(prefix="pdf_attachment_")
            temp_path = os.path.join(temp_dir, fn)
            with open(temp_path, "wb") as f:
                f.write(data)
            os.startfile(temp_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir adjunto", f"No se pudo abrir '{fn}':\n{exc}")

    def save_selected(self):
        att = self._selected_item_data()
        if not att:
            return
        fn = att["filename"]
        target, _ = QFileDialog.getSaveFileName(self, "Guardar archivo adjunto", fn)
        if not target:
            return
        try:
            data = get_attachment_bytes(self.doc, att)
            with open(target, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Archivo guardado", f"Se guardó '{fn}' correctamente.")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar el archivo:\n{exc}")

    def extract_all(self):
        if self.count() == 0:
            return
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta para extraer todos los adjuntos")
        if not folder:
            return
        saved_count = 0
        attachments = get_all_attachments(self.doc)
        for att in attachments:
            fn = att["filename"]
            target = os.path.join(folder, fn)
            # Evitar colisión de nombres
            base, ext = os.path.splitext(target)
            cnt = 1
            while os.path.exists(target):
                target = f"{base}_{cnt}{ext}"
                cnt += 1
            try:
                data = get_attachment_bytes(self.doc, att)
                with open(target, "wb") as f:
                    f.write(data)
                saved_count += 1
            except Exception:
                pass
        QMessageBox.information(
            self,
            "Extracción completada",
            f"Se extrajeron {saved_count} de {len(attachments)} archivos en:\n{folder}",
        )

    def add_attachment(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo para adjuntar al PDF")
        if not file_path:
            return
        try:
            fn = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                data = f.read()
            self.doc.embfile_add(fn, data, filename=fn, ufilename=fn)
            self.reload()
            self.attachmentChanged.emit()
            QMessageBox.information(self, "Archivo adjuntado", f"Se adjuntó '{fn}' al PDF.\nRecuerda guardar los cambios (Ctrl+S).")
        except Exception as exc:
            QMessageBox.critical(self, "Error al adjuntar", f"No se pudo adjuntar el archivo:\n{exc}")

    def delete_selected(self):
        att = self._selected_item_data()
        if not att:
            return
        fn = att["filename"]
        r = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Deseas eliminar el archivo adjunto '{fn}' del documento?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        try:
            if att.get("source") == "annot":
                annot = att.get("annot")
                pno = att.get("page", 0)
                if annot is not None:
                    self.doc[pno].delete_annot(annot)
            else:
                self.doc.embfile_del(att.get("index", 0))
            self.reload()
            self.attachmentChanged.emit()
            QMessageBox.information(self, "Archivo eliminado", f"Se eliminó '{fn}'.\nRecuerda guardar los cambios (Ctrl+S).")
        except Exception as exc:
            QMessageBox.critical(self, "Error al eliminar", f"No se pudo eliminar el adjunto:\n{exc}")

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            att = item.data(0, Qt.UserRole)
            fn = att["filename"]
            ext = os.path.splitext(fn)[1].lower()
            act_open = menu.addAction(f"Abrir '{fn}'")
            act_open.triggered.connect(lambda: self._open_attachment(att))

            if ext == ".pdf":
                act_open_ext = menu.addAction("Abrir con aplicación externa")
                def _open_ext():
                    try:
                        d = get_attachment_bytes(self.doc, att)
                        td = tempfile.mkdtemp(prefix="pdf_attachment_")
                        tp = os.path.join(td, fn)
                        with open(tp, "wb") as f:
                            f.write(d)
                        os.startfile(tp)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", str(e))
                act_open_ext.triggered.connect(_open_ext)

            act_save = menu.addAction("Guardar como…")
            act_save.triggered.connect(self.save_selected)
            menu.addSeparator()

        act_extract_all = menu.addAction("Extraer todos los adjuntos a una carpeta…")
        act_extract_all.triggered.connect(self.extract_all)
        menu.addSeparator()
        act_add = menu.addAction("Adjuntar nuevo archivo…")
        act_add.triggered.connect(self.add_attachment)

        if item is not None:
            act_del = menu.addAction("Eliminar adjunto")
            act_del.triggered.connect(self.delete_selected)

        menu.exec(self.tree.viewport().mapToGlobal(pos))
