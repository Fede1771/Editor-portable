"""Gestión y visualización de archivos adjuntos embebidos en el PDF."""
from __future__ import annotations

import os
import re
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
    ".hta", ".cpl", ".lnk", ".iso", ".chm", ".url", ".docm", ".xlsm", ".pptm",
    ".dotm", ".xltm", ".potm", ".wsc", ".inf", ".scf",
    ".msp", ".mst", ".appx", ".msix", ".appref-ms", ".settingcontent-ms", ".library-ms",
    ".img", ".vhd", ".vhdx", ".application", ".gadget", ".msc", ".ps1xml", ".psc1",
    ".psd1", ".sys", ".drv", ".ocx", ".xll", ".xlam", ".ppam", ".sldm", ".xlsb",
    ".one", ".website", ".vb", ".shb", ".shs", ".ws", ".sct", ".py", ".pyw",
}

# H40: política explícita de tipos que se consideran pasivos y pueden despacharse a la
# aplicación asociada sin confirmación. Todo lo demás requiere guardar para revisión
# (tipos activos) o confirmación informada (tipos desconocidos).
PASSIVE_EXTENSIONS = {
    ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".xml", ".json",
    ".mp3", ".wav", ".mp4", ".zip", ".eml", ".msg",
}

_RESERVED_DEVICE_NAMES = (
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}
    | {"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
)
_MAX_NAME_LEN = 180

KIND_PDF = "pdf"
KIND_PASSIVE = "passive"
KIND_ACTIVE = "active"
KIND_UNKNOWN = "unknown"


def safe_local_name(name: str) -> str:
    """Genera un nombre de archivo local seguro a partir del nombre (no confiable) declarado en el PDF.

    - Elimina cualquier componente de ruta (relativa, absoluta, unidad, UNC).
    - Neutraliza flujos alternativos NTFS (``:``), caracteres reservados y de control.
    - Quita puntos y espacios finales (Windows los descarta al crear el archivo).
    - Antepone ``_`` a nombres de dispositivo reservados (CON, NUL, COM1, …).
    """
    raw = (name or "").replace("\\", "/")
    base = raw.rsplit("/", 1)[-1]
    # Unidades ("C:archivo") y ADS ("archivo:stream") -> se cortan en el primer ':' significativo
    base = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", base)
    base = base.strip(" .\t")
    if base in ("", "_") or set(base) <= {".", "_", " "}:
        base = "adjunto.dat"
    stem, dot, ext = base.partition(".")
    if stem.upper().rstrip(" ") in _RESERVED_DEVICE_NAMES:
        base = "_" + base
    if len(base) > _MAX_NAME_LEN:
        root, ext2 = os.path.splitext(base)
        base = root[: _MAX_NAME_LEN - len(ext2)] + ext2
    return base


def sanitize_attachment_name(name: str) -> str:
    """Compatibilidad: alias de :func:`safe_local_name`."""
    return safe_local_name(name)


def canonical_extension(name: str) -> str:
    """Extensión efectiva que usará Windows para el nombre dado (tras normalizarlo)."""
    return os.path.splitext(safe_local_name(name))[1].lower()


def classify_attachment(name: str) -> str:
    """Clasifica un adjunto según la extensión canónica: pdf / passive / active / unknown."""
    ext = canonical_extension(name)
    if ext == ".pdf":
        return KIND_PDF
    if ext in DANGEROUS_EXTENSIONS:
        return KIND_ACTIVE
    if ext in PASSIVE_EXTENSIONS:
        return KIND_PASSIVE
    return KIND_UNKNOWN


def contained_path(root: str, name: str) -> str:
    """Devuelve la ruta absoluta de ``name`` dentro de ``root`` o lanza ValueError si escaparía."""
    root_abs = os.path.realpath(os.path.abspath(root))
    target = os.path.realpath(os.path.abspath(os.path.join(root_abs, safe_local_name(name))))
    if os.path.dirname(target) != root_abs:
        raise ValueError("Ruta de destino fuera de la carpeta permitida.")
    return target


def unique_path(path: str) -> str:
    """Evita colisiones: agrega un sufijo numérico si el archivo ya existe."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    cnt = 1
    while os.path.exists(f"{base}_{cnt}{ext}"):
        cnt += 1
    return f"{base}_{cnt}{ext}"


# ------------------------------------------------------------------ H41 procedencia (MOTW)
UNTRUSTED_ZONE = 3  # Internet


def read_zone_id(path: str | None) -> int | None:
    """Lee el ZoneId del flujo Zone.Identifier (Mark of the Web) de un archivo, si existe."""
    if not path:
        return None
    try:
        with open(path + ":Zone.Identifier", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.strip().lower().startswith("zoneid="):
                    return int(line.split("=", 1)[1].strip())
    except (OSError, ValueError):
        return None
    return None


def write_mark_of_the_web(path: str, source_path: str | None = None) -> bool:
    """Marca un archivo extraído como de procedencia no confiable.

    Política: el contenido embebido en un PDF se trata siempre como externo. Se propaga el ZoneId
    del PDF contenedor si es igual o más restrictivo que Internet (3); en otro caso se asigna 3.
    Devuelve False si el sistema de archivos no admite la marca (p. ej. FAT32).
    """
    zone = read_zone_id(source_path)
    zone = zone if zone is not None and zone >= UNTRUSTED_ZONE else UNTRUSTED_ZONE
    try:
        with open(path + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write(f"[ZoneTransfer]\r\nZoneId={zone}\r\n")
        return True
    except OSError:
        return False


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
    # H15: no se conserva el wrapper Annot (queda huérfano si la página se recolecta o el
    # documento se reemplaza); se guarda página + xref y se recarga desde una página viva.
    for pno in range(doc.page_count):
        page = doc[pno]
        for annot in page.annots(types=[fitz.PDF_ANNOT_FILE_ATTACHMENT]):
            info = getattr(annot, "file_info", {}) or {}
            fn = info.get("filename") or info.get("ufilename") or f"adjunto_pag_{pno+1}"
            size = info.get("size") or info.get("length") or 0
            items.append({
                "source": "annot",
                "page": pno,
                "xref": annot.xref,
                "name": fn,
                "filename": fn,
                "size": size,
                "date": "",
                "desc": f"En página {pno + 1}",
            })

    return items


def _load_annot(doc: fitz.Document, item: dict):
    page = doc[item.get("page", 0)]
    annot = page.load_annot(item["xref"])
    return page, annot


def get_attachment_bytes(doc: fitz.Document, item: dict) -> bytes:
    """Extrae los bytes crudos del archivo adjunto seleccionado."""
    if item.get("source") == "annot":
        page, annot = _load_annot(doc, item)
        if annot is None:
            raise ValueError("La anotación del adjunto ya no existe en el documento.")
        data = annot.get_file() or b""
        del annot, page
        return data
    idx = item.get("index", 0)
    return doc.embfile_get(idx)


def delete_attachment(doc: fitz.Document, item: dict) -> None:
    """Elimina el adjunto indicado (de catálogo o de anotación) del documento dado."""
    if item.get("source") == "annot":
        page, annot = _load_annot(doc, item)
        if annot is not None:
            page.delete_annot(annot)
    else:
        doc.embfile_del(item.get("index", 0))


class AttachmentWidget(QWidget):
    """Panel lateral interactivo para explorar, abrir, extraer y gestionar archivos adjuntos."""

    openPdfRequested = Signal(bytes, str)  # (pdf_bytes, filename)
    attachmentChanged = Signal()          # Cuando se agrega o elimina un adjunto

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.icon_provider = QFileIconProvider()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nombre", "Tamaño"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Barra de botones compacta en 2 filas para no forzar el ancho del panel lateral
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setSpacing(3)

        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self.btn_open = QPushButton("Abrir")
        self.btn_open.setToolTip("Abrir el archivo adjunto seleccionado")
        self.btn_open.clicked.connect(self.open_selected)

        self.btn_save = QPushButton("Guardar…")
        self.btn_save.setToolTip("Guardar el archivo seleccionado en el disco")
        self.btn_save.clicked.connect(self.save_selected)

        self.btn_extract_all = QPushButton("Extraer todo…")
        self.btn_extract_all.setToolTip("Guardar todos los adjuntos en una carpeta")
        self.btn_extract_all.clicked.connect(self.extract_all)

        row1.addWidget(self.btn_open)
        row1.addWidget(self.btn_save)
        row1.addWidget(self.btn_extract_all)

        row2 = QHBoxLayout()
        row2.setSpacing(3)
        self.btn_add = QPushButton("+ Adjuntar…")
        self.btn_add.setToolTip("Incrustar un nuevo archivo dentro del PDF")
        self.btn_add.clicked.connect(self.add_attachment)

        self.btn_del = QPushButton("Eliminar")
        self.btn_del.setToolTip("Eliminar el archivo adjunto del PDF")
        self.btn_del.clicked.connect(self.delete_selected)

        row2.addWidget(self.btn_add)
        row2.addWidget(self.btn_del)

        btn_layout.addLayout(row1)
        btn_layout.addLayout(row2)

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
            item = QTreeWidgetItem([fn, sz])
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

    def _source_path(self) -> str | None:
        p = self.parent()
        while p is not None:
            if hasattr(p, "path") and getattr(p, "path"):
                return getattr(p, "path")
            p = p.parent() if hasattr(p, "parent") else None
        return getattr(self.doc, "name", None) or None

    def _run_doc_edit(self, fn: Callable[[fitz.Document], None]) -> None:
        """Ejecuta una mutación dentro de la transacción Undo/Redo de la pestaña si existe (H24)."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "run_edit"):
                p.run_edit(fn)
                return
            p = p.parent() if hasattr(p, "parent") else None
        fn(self.doc)
        self.reload()
        self.attachmentChanged.emit()

    def _write_extracted_file(self, target_path: str, data: bytes) -> None:
        with open(target_path, "wb") as f:
            f.write(data)
        write_mark_of_the_web(target_path, source_path=self._source_path())

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

            # H02/H40: normalizar SIEMPRE antes de clasificar la extensión
            safe_name = safe_local_name(fn)
            ext = canonical_extension(safe_name)
            kind = classify_attachment(safe_name)

            if kind == KIND_ACTIVE:
                r = QMessageBox.warning(
                    self,
                    "Advertencia de seguridad",
                    f"El archivo adjunto «{safe_name}» tiene una extensión activa o ejecutable ({ext}).\n\n"
                    "Ejecutar este tipo de archivos directamente puede comprometer la seguridad de tu equipo "
                    "si el PDF proviene de un origen desconocido.\n\n"
                    "Por seguridad, el editor no lo ejecutará automáticamente.\n"
                    "¿Deseas guardarlo en una carpeta para analizarlo previamente?",
                    QMessageBox.Save | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if r == QMessageBox.Save:
                    self.save_selected()
                return

            if kind == KIND_UNKNOWN:
                r = QMessageBox.warning(
                    self,
                    "Tipo de adjunto no verificado",
                    f"El archivo adjunto «{safe_name}» tiene un tipo ({ext or 'sin extensión'}) que no figura "
                    "en la lista de formatos pasivos permitidos para apertura directa.\n\n"
                    "Por seguridad, no se abrirá automáticamente con una aplicación externa.\n"
                    "¿Deseas guardarlo en disco para revisarlo manualmente?",
                    QMessageBox.Save | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if r == QMessageBox.Save:
                    self.save_selected()
                return

            if kind == KIND_PDF:
                self.openPdfRequested.emit(data, safe_name)
                return

            # Revalidación inmediata antes del despacho al sistema (H40)
            if classify_attachment(safe_name) != KIND_PASSIVE:
                raise ValueError("El tipo de archivo no está habilitado para apertura directa.")

            from .privacy import TempManager
            temp_dir = TempManager.create_temp_dir(prefix="pdf_attachment_")
            temp_path = contained_path(temp_dir, safe_name)
            self._write_extracted_file(temp_path, data)
            os.startfile(temp_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir adjunto", f"No se pudo abrir '{fn}':\n{exc}")

    def save_selected(self):
        att = self._selected_item_data()
        if not att:
            return
        fn = safe_local_name(att["filename"])
        target, _ = QFileDialog.getSaveFileName(self, "Guardar archivo adjunto", fn)
        if not target:
            return
        try:
            data = get_attachment_bytes(self.doc, att)
            self._write_extracted_file(target, data)
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
            try:
                target = unique_path(contained_path(folder, att["filename"]))
                data = get_attachment_bytes(self.doc, att)
                self._write_extracted_file(target, data)
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
            fn = safe_local_name(os.path.basename(file_path))
            with open(file_path, "rb") as f:
                data = f.read()
            self._run_doc_edit(lambda d: d.embfile_add(fn, data, filename=fn, ufilename=fn))
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
            spec = dict(att)
            self._run_doc_edit(lambda d: delete_attachment(d, spec))
            QMessageBox.information(self, "Archivo eliminado", f"Se eliminó '{fn}'.\nRecuerda guardar los cambios (Ctrl+S).")
        except Exception as exc:
            QMessageBox.critical(self, "Error al eliminar", f"No se pudo eliminar el adjunto:\n{exc}")

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            att = item.data(0, Qt.UserRole)
            fn = safe_local_name(att["filename"])
            ext = canonical_extension(fn)
            act_open = menu.addAction(f"Abrir '{fn}'")
            act_open.triggered.connect(lambda: self._open_attachment(att))

            if ext == ".pdf":
                act_open_ext = menu.addAction("Abrir con aplicación externa")
                def _open_ext():
                    try:
                        d = get_attachment_bytes(self.doc, att)
                        from .privacy import TempManager
                        td = TempManager.create_temp_dir(prefix="pdf_attachment_")
                        tp = contained_path(td, fn)
                        self._write_extracted_file(tp, d)
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
