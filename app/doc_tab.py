"""Pestaña de documento: visor + panel lateral (miniaturas y marcadores) + edición con deshacer."""
from __future__ import annotations

import os
import tempfile

import pymupdf as fitz
from PySide6.QtCore import QItemSelectionModel, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QSplitter, QStyle, QStyledItemDelegate, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .viewer import PdfView
from .attachments import AttachmentWidget
from .search_bar import FloatingSearchBar
from .security import SecurityBanner, scan_document_security, sanitize_document

THUMB_W = 120
UNDO_LIMIT = 15


class ThumbnailDelegate(QStyledItemDelegate):
    """Renderizado centrado de cada miniatura sin huecos laterales, adaptativo al ancho del panel."""

    def sizeHint(self, option, index):
        thumb_h = int(THUMB_W * 1.42)
        return QSize(option.rect.width() if option.rect.width() > 0 else (THUMB_W + 24), thumb_h + 30)

    def paint(self, painter: QPainter, option, index):
        rect = option.rect
        thumb_h = int(THUMB_W * 1.42)
        thumb_w = THUMB_W
        x = rect.x() + max(0, (rect.width() - thumb_w) // 2)
        y = rect.y() + 4

        # Resaltado de selección centrado alrededor de la miniatura
        if option.state & QStyle.State_Selected:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            card_rect = QRect(x - 6, y - 2, thumb_w + 12, thumb_h + 24)
            painter.setBrush(QColor(0, 120, 215, 30))
            painter.setPen(QPen(QColor(0, 120, 215), 1.5))
            painter.drawRoundedRect(card_rect, 6, 6)
            painter.restore()

        # Dibujo de la miniatura
        icon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            pix = icon.pixmap(QSize(thumb_w, thumb_h))
            if not pix.isNull():
                tw = pix.width()
                th = pix.height()
                tx = rect.x() + max(0, (rect.width() - tw) // 2)
                ty = y + (thumb_h - th) // 2
                painter.fillRect(QRect(tx + 2, ty + 2, tw, th), QColor(0, 0, 0, 30))
                painter.drawPixmap(tx, ty, pix)
                painter.setPen(QColor(180, 180, 180))
                painter.drawRect(tx, ty, tw, th)

        # Número de página centrado abajo
        p_str = index.data(Qt.DisplayRole)
        if p_str:
            painter.save()
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            is_sel = bool(option.state & QStyle.State_Selected)
            painter.setPen(QColor(0, 100, 200) if is_sel else QColor(50, 50, 50))
            painter.drawText(QRect(rect.x(), y + thumb_h + 2, rect.width(), 18), Qt.AlignCenter, str(p_str))
            painter.restore()


class ThumbnailList(QListWidget):
    """Miniaturas con selección múltiple y reordenado arrastrando.

    Las miniaturas se generan de a poco para no congelar la interfaz.
    """

    ORIG_ROLE = Qt.UserRole
    orderChanged = Signal(list, list)   # nuevo orden (índices originales), filas seleccionadas

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setViewMode(QListWidget.ListMode)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setItemDelegate(ThumbnailDelegate(self))
        self.setSpacing(6)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._next = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fill_batch)
        self.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._emit_order))
        self.rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport().update()

    def rebuild(self, select: list[int] | None = None):
        self._timer.stop()
        self.blockSignals(True)
        self.clear()
        thumb_h = int(THUMB_W * 1.42)
        for i in range(self.doc.page_count):
            item = QListWidgetItem(str(i + 1))
            item.setData(self.ORIG_ROLE, i)
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(THUMB_W + 20, thumb_h + 28))
            self.addItem(item)
        for r in select or []:
            if 0 <= r < self.count():
                self.item(r).setSelected(True)
        if select:
            self.setCurrentRow(select[0], QItemSelectionModel.NoUpdate)
        self.blockSignals(False)
        self._next = 0
        self._timer.start(15)

    def selected_rows(self) -> list[int]:
        return sorted(self.row(i) for i in self.selectedItems())

    def _emit_order(self):
        order = [self.item(r).data(self.ORIG_ROLE) for r in range(self.count())]
        if order != list(range(len(order))):
            self.orderChanged.emit(order, self.selected_rows())

    def _fill_batch(self):
        for _ in range(4):
            if self._next >= self.doc.page_count:
                self._timer.stop()
                return
            self._set_icon(self._next)
            self._next += 1

    def _set_icon(self, i: int):
        page = self.doc[i]
        scale = THUMB_W / max(1.0, page.rect.width)
        pm = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        item = self.item(i)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(img)))

    def select_page(self, index: int):
        """Sigue a la página actual del visor sin romper una selección múltiple."""
        if not (0 <= index < self.count()):
            return
        if len(self.selectedItems()) > 1:
            self.scrollToItem(self.item(index))
            return
        if self.currentRow() != index or not self.selectedItems():
            self.blockSignals(True)
            self.setCurrentRow(index)
            self.scrollToItem(self.item(index))
            self.blockSignals(False)


class BookmarkTree(QTreeWidget):
    """Árbol de marcadores (tabla de contenidos) del PDF."""

    PAGE_ROLE = Qt.UserRole

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.load(doc)

    def load(self, doc: fitz.Document):
        self.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, title, page in doc.get_toc(simple=True):
            item = QTreeWidgetItem([title])
            item.setData(0, self.PAGE_ROLE, max(0, page - 1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.addTopLevelItem(item)
            stack.append((level, item))
        self.expandToDepth(0)


class CommentTree(QTreeWidget):
    """Árbol de comentarios y anotaciones embebidas agrupadas por página."""

    PAGE_ROLE = Qt.UserRole
    RECT_ROLE = Qt.UserRole + 1

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Comentarios"])
        self.setAnimated(True)
        self.load(doc)

    def load(self, doc: fitz.Document) -> int:
        from . import annotations as annot_mod
        self.clear()
        annots = annot_mod.get_all_comments_and_annots(doc)
        by_page: dict[int, list[dict]] = {}
        for a in annots:
            by_page.setdefault(a["page"], []).append(a)

        total_comments = len(annots)
        for pno in sorted(by_page.keys()):
            items = by_page[pno]
            page_item = QTreeWidgetItem([f"Página {pno + 1} ({len(items)})"])
            page_item.setData(0, self.PAGE_ROLE, pno)
            font = page_item.font(0)
            font.setBold(True)
            page_item.setFont(0, font)

            for a in items:
                atype = a["type"]
                author = a["author"]
                content = a["content"]
                label = f"[{atype}] {author}: {content}" if author != "Sin autor" else f"[{atype}] {content}"
                child = QTreeWidgetItem([label])
                child.setData(0, self.PAGE_ROLE, pno)
                child.setData(0, self.RECT_ROLE, a["rect"])
                child.setToolTip(0, f"Tipo: {atype}\nAutor: {author}\nFecha: {a.get('date', '')}\nTexto: {content}")
                page_item.addChild(child)

            self.addTopLevelItem(page_item)

        self.expandAll()
        return total_comments


class _DocSnapshot:
    """Instantánea de documento para Undo/Redo.
    Para PDFs estándar (<15 MB) permanece en memoria RAM para máxima velocidad.
    Para PDFs de gran peso (>=15 MB) se vuelca temporalmente a disco para evitar
    saturación de memoria.
    """

    DISK_THRESHOLD = 15 * 1024 * 1024  # 15 MB

    def __init__(self, data: bytes):
        self._size = len(data)
        self._temp_path: str | None = None
        if self._size >= self.DISK_THRESHOLD:
            from .privacy import TempManager
            fd, path = TempManager.create_temp_file(prefix="editorpdf_snap_", suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            self._temp_path = path
            self._data: bytes | None = None
        else:
            self._data = data

    def get_bytes(self) -> bytes:
        if self._data is not None:
            return self._data
        if self._temp_path and os.path.isfile(self._temp_path):
            with open(self._temp_path, "rb") as f:
                return f.read()
        return b""

    def cleanup(self) -> None:
        if self._temp_path:
            try:
                from .privacy import TempManager
                TempManager.cleanup_path(self._temp_path)
            except Exception:
                pass
            self._temp_path = None
        self._data = None

    def __del__(self):
        self.cleanup()


class DocTab(QWidget):
    """Un documento abierto, con historial de cambios (deshacer / rehacer)."""

    edited = Signal()   # cambió el contenido o el estado de modificado
    openPdfAttachmentRequested = Signal(bytes, str)  # (bytes, filename) para abrir adjuntos PDF

    def __init__(self, path: str, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.path = path
        self.doc = doc
        self.modified = False
        self.save_as_only = False
        self.suggested = "documento.pdf"
        self._undo: list[_DocSnapshot] = []
        self._redo: list[_DocSnapshot] = []

        self.view = PdfView(doc)
        self.thumbs = ThumbnailList(doc)
        self.bookmarks = BookmarkTree(doc)
        self.comments = CommentTree(doc)
        self.attachments = AttachmentWidget(doc, parent=self)

        self.side = QTabWidget()
        self.side.setTabPosition(QTabWidget.West)
        self.side.setStyleSheet("""
            QTabBar::tab {
                min-width: 30px;
                max-width: 36px;
                padding: 10px 4px;
                font-size: 13pt;
            }
        """)
        self.side.addTab(self.thumbs, "📄")
        self.side.addTab(self.bookmarks, "📑")
        self.side.addTab(self.comments, "💬")
        self.side.addTab(self.attachments, "📎")
        self.side.setTabToolTip(0, "Miniaturas de páginas")
        self.side.setTabToolTip(1, "Marcadores / Índice")
        self.side.setTabToolTip(2, "Comentarios y notas")
        self.side.setTabToolTip(3, "Archivos adjuntos embebidos")
        self._sync_side_tabs()

        self.security_banner = SecurityBanner(self)
        self.security_banner.sanitizeRequested.connect(self.sanitize_security)

        self.search_bar = FloatingSearchBar()
        view_container = QWidget()
        view_layout = QVBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)
        view_layout.addWidget(self.security_banner)
        view_layout.addWidget(self.search_bar)
        view_layout.addWidget(self.view)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.side)
        self.splitter.addWidget(view_container)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([190, 950])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        # Plegado inteligente del panel lateral para documentos simples (<= 2 págs sin anexos)
        if (
            doc.page_count <= 2
            and self.bookmarks.topLevelItemCount() == 0
            and self.comments.topLevelItemCount() == 0
            and self.attachments.count() == 0
        ):
            self.side.hide()

        self.thumbs.currentRowChanged.connect(self.view.goto_page)
        self.bookmarks.itemClicked.connect(
            lambda item, _c: self.view.goto_page(item.data(0, BookmarkTree.PAGE_ROLE))
        )
        self.comments.itemClicked.connect(self._on_comment_clicked)
        self.attachments.openPdfRequested.connect(self.openPdfAttachmentRequested)
        self.attachments.attachmentChanged.connect(self._on_attachment_changed)
        self.view.pageChanged.connect(self.thumbs.select_page)
        self.thumbs.orderChanged.connect(self._on_order_changed)
        self.thumbs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumbs.customContextMenuRequested.connect(self._on_thumb_context_menu)

        self.search_bar.searchTextChanged.connect(self._on_search_text)
        self.search_bar.findNext.connect(self._find_next)
        self.search_bar.findPrev.connect(self._find_prev)
        self.search_bar.closed.connect(self.view.clear_search)
        self.view.searchRequested.connect(self.show_search)
        self.check_security()

    def check_security(self):
        """Verifica pasivamente si el documento contiene scripts o acciones automáticas."""
        sec = scan_document_security(self.doc)
        if sec.get("has_threats"):
            self.security_banner.show_threats(sec)
        else:
            self.security_banner.hide()

    def sanitize_security(self):
        """Desactiva y remueve permanentemente scripts y acciones del documento."""
        self.push_undo()
        cleaned = sanitize_document(self.doc)
        self.modified = True
        self.security_banner.show_cleaned()
        self.edited.emit()

    def _on_attachment_changed(self):
        self.modified = True
        self._sync_side_tabs()
        self.edited.emit()

    def _on_comment_clicked(self, item, _c):
        pno = item.data(0, CommentTree.PAGE_ROLE)
        if pno is not None:
            rect = item.data(0, CommentTree.RECT_ROLE)
            if rect:
                self.view.scroll_to_page_rect(pno, rect)
            else:
                self.view.goto_page(pno)

    def _on_thumb_context_menu(self, pos):
        item = self.thumbs.itemAt(pos)
        if item is not None and not item.isSelected():
            self.thumbs.clearSelection()
            item.setSelected(True)
            self.thumbs.setCurrentItem(item)

        sel = self.thumbs.selected_rows()
        if not sel:
            p = self.view.current_page
            if 0 <= p < self.doc.page_count:
                sel = [p]

        if not sel:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #c8ccd0;
                border-radius: 6px;
                padding: 4px;
                font-size: 9pt;
            }
            QMenu::item {
                padding: 6px 24px 6px 10px;
                border-radius: 4px;
                color: #202124;
            }
            QMenu::item:selected {
                background-color: #e8f0fe;
                color: #1a73e8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #dadce0;
                margin: 4px 6px;
            }
        """)

        num_txt = f"{len(sel)} página{'s' if len(sel) > 1 else ''}"

        act_rot_cw = menu.addAction("🔄 Girar 90° a la derecha")
        act_rot_cw.triggered.connect(lambda: self._rotate_thumb_pages(sel, 90))

        act_rot_ccw = menu.addAction("🔄 Girar 90° a la izquierda")
        act_rot_ccw.triggered.connect(lambda: self._rotate_thumb_pages(sel, 270))

        menu.addSeparator()

        act_dup = menu.addAction(f"📋 Duplicar {num_txt}")
        act_dup.triggered.connect(lambda: self._duplicate_thumb_pages(sel))

        act_del = menu.addAction(f"🗑 Eliminar {num_txt}")
        act_del.triggered.connect(lambda: self._delete_thumb_pages(sel))

        menu.addSeparator()

        last_p = sel[-1]
        act_blank = menu.addAction("📄 Insertar página en blanco después")
        act_blank.triggered.connect(lambda: self._insert_blank_after(last_p))

        act_extract = menu.addAction(f"📤 Extraer {num_txt} a nuevo PDF…")
        act_extract.triggered.connect(lambda: self._extract_thumb_pages(sel))

        menu.exec(self.thumbs.viewport().mapToGlobal(pos))

    def _rotate_thumb_pages(self, pages: list[int], angle: int):
        from . import operations as ops
        self.run_edit(lambda d: ops.rotate_pages(d, pages, angle), select=pages)

    def _duplicate_thumb_pages(self, pages: list[int]):
        from . import operations as ops
        self.run_edit(lambda d: ops.duplicate_pages(d, pages), select=pages)

    def _delete_thumb_pages(self, pages: list[int]):
        from . import operations as ops
        if len(pages) >= self.doc.page_count:
            QMessageBox.warning(self, "No permitido", "No puedes eliminar todas las páginas del documento.")
            return
        r = QMessageBox.question(
            self,
            "Eliminar páginas",
            f"¿Deseas eliminar {len(pages)} página(s) seleccionada(s)?\nEsta acción se puede deshacer con Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if r == QMessageBox.Yes:
            self.run_edit(lambda d: ops.delete_pages(d, pages))

    def _insert_blank_after(self, page_idx: int):
        from . import operations as ops
        target = page_idx + 1
        self.run_edit(lambda d: ops.insert_blank(d, target, like=page_idx), select=[target], goto=target)

    def _extract_thumb_pages(self, pages: list[int]):
        from . import operations as ops
        base = os.path.splitext(self.path)[0] if self.path else "documento"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar páginas extraídas",
            f"{base}_paginas.pdf",
            "Documentos PDF (*.pdf)",
        )
        if out_path:
            ops.extract_pages(self.doc, pages, out_path)
            QMessageBox.information(
                self,
                "Páginas extraídas",
                f"Se han extraído {len(pages)} página(s) correctamente en:\n{out_path}",
            )

    # ------------------------------------------------------------------ datos
    @property
    def title(self) -> str:
        return ("• " if self.modified else "") + (os.path.basename(self.path) or "Sin título")

    def selected_pages(self) -> list[int]:
        rows = self.thumbs.selected_rows()
        return rows if rows else [self.view.current_page]

    def toggle_sidebar(self):
        self.side.setVisible(not self.side.isVisible())

    def _sync_side_tabs(self):
        has_bm = self.bookmarks.topLevelItemCount() > 0
        self.side.setTabEnabled(1, has_bm)
        total_c = self.comments.topLevelItemCount()
        self.side.setTabText(2, "💬")
        self.side.setTabToolTip(2, f"Comentarios ({total_c})" if total_c else "Comentarios (0)")
        total_att = self.attachments.count()
        self.side.setTabText(3, "📎")
        self.side.setTabToolTip(3, f"Archivos adjuntos ({total_att})" if total_att else "Archivos adjuntos (0)")
        if not has_bm and self.side.currentIndex() == 1:
            self.side.setCurrentIndex(0)

    # --------------------------------------------------------------- búsqueda
    def show_search(self, initial_text: str = ""):
        self.search_bar.show_and_focus(initial_text)
        if initial_text:
            self._on_search_text(initial_text)

    def _on_search_text(self, text: str):
        total = self.view.search(text)
        if total > 0:
            i, n = self.view.next_hit()
            self.search_bar.set_result_status(i, n)
        else:
            self.search_bar.set_result_status(0, 0)

    def _find_next(self):
        i, n = self.view.next_hit()
        self.search_bar.set_result_status(i, n)

    def _find_prev(self):
        i, n = self.view.prev_hit()
        self.search_bar.set_result_status(i, n)

    # --------------------------------------------------------------- edición
    @staticmethod
    def _clear_snapshots(snapshots: list[_DocSnapshot]) -> None:
        for s in snapshots:
            s.cleanup()
        snapshots.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def run_edit(self, fn, select: list[int] | None = None, goto: int | None = None):
        """Aplica `fn(doc)` guardando una copia para deshacer. Si falla, restaura el documento."""
        snapshot = _DocSnapshot(self.doc.tobytes())
        try:
            fn(self.doc)
        except Exception:
            self._load_bytes(snapshot.get_bytes())
            self.view.reload(self.doc)
            snapshot.cleanup()
            raise
        self._undo.append(snapshot)
        while len(self._undo) > UNDO_LIMIT:
            old_snap = self._undo.pop(0)
            old_snap.cleanup()
        self._clear_snapshots(self._redo)
        self.modified = True
        self._refresh(select, goto)

    def undo(self):
        if self._undo:
            snap = self._undo.pop()
            self._redo.append(_DocSnapshot(self.doc.tobytes()))
            while len(self._redo) > UNDO_LIMIT:
                old_snap = self._redo.pop(0)
                old_snap.cleanup()
            self._load_bytes(snap.get_bytes())
            snap.cleanup()
            self.modified = True
            self._refresh()

    def redo(self):
        if self._redo:
            snap = self._redo.pop()
            self._undo.append(_DocSnapshot(self.doc.tobytes()))
            while len(self._undo) > UNDO_LIMIT:
                old_snap = self._undo.pop(0)
                old_snap.cleanup()
            self._load_bytes(snap.get_bytes())
            snap.cleanup()
            self.modified = True
            self._refresh()

    def _load_bytes(self, data: bytes):
        new = fitz.open("pdf", data)
        old = self.doc
        self.doc = new
        self.thumbs.doc = new
        self.view.doc = new
        self.attachments.doc = new
        old.close()

    def _refresh(self, select: list[int] | None = None, goto: int | None = None):
        self.view.reload(self.doc)
        self.thumbs.rebuild(select)
        self.bookmarks.load(self.doc)
        self.comments.load(self.doc)
        self.attachments.reload()
        self._sync_side_tabs()
        if goto is not None:
            self.view.goto_page(goto)
        elif select:
            self.view.goto_page(select[0])
        self.edited.emit()

    def _on_order_changed(self, order: list[int], selected_rows: list[int]):
        from . import operations as ops
        try:
            self.run_edit(lambda d: ops.reorder(d, order), select=selected_rows)
        except Exception:  # noqa: BLE001
            self.thumbs.rebuild()

    # ---------------------------------------------------------------- guardar
    def save(self, path: str | None = None):
        """Guarda de forma segura (archivo temporal + reemplazo)."""
        target = path or self.path
        tmp = target + ".tmp"
        try:
            self.doc.save(tmp, garbage=3, deflate=True)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        self.path = target
        self.modified = False
        self.edited.emit()

    def close_document(self):
        self.thumbs._timer.stop()
        self._clear_snapshots(self._undo)
        self._clear_snapshots(self._redo)
        self.doc.close()
