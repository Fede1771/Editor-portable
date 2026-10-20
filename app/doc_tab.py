"""Pestaña de documento: visor + panel lateral (miniaturas y marcadores) + edición con deshacer."""
from __future__ import annotations

import os

import pymupdf as fitz
from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .viewer import PdfView
from .attachments import AttachmentWidget

THUMB_W = 120
UNDO_LIMIT = 15


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
        self.setMovement(QListWidget.Snap)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.42)))
        self.setSpacing(4)
        self._next = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fill_batch)
        self.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._emit_order))
        self.rebuild()

    def rebuild(self, select: list[int] | None = None):
        self._timer.stop()
        self.blockSignals(True)
        self.clear()
        for i in range(self.doc.page_count):
            item = QListWidgetItem(str(i + 1))
            item.setData(self.ORIG_ROLE, i)
            item.setTextAlignment(Qt.AlignHCenter)
            item.setSizeHint(QSize(THUMB_W + 24, int(THUMB_W * 1.42) + 28))
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
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []

        self.view = PdfView(doc)
        self.thumbs = ThumbnailList(doc)
        self.bookmarks = BookmarkTree(doc)
        self.comments = CommentTree(doc)
        self.attachments = AttachmentWidget(doc, parent=self)

        self.side = QTabWidget()
        self.side.setTabPosition(QTabWidget.West)
        self.side.addTab(self.thumbs, "Miniaturas")
        self.side.addTab(self.bookmarks, "Marcadores")
        self.side.addTab(self.comments, "Comentarios")
        self.side.addTab(self.attachments, "Adjuntos")
        self._sync_side_tabs()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.side)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([220, 900])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self.thumbs.currentRowChanged.connect(self.view.goto_page)
        self.bookmarks.itemClicked.connect(
            lambda item, _c: self.view.goto_page(item.data(0, BookmarkTree.PAGE_ROLE))
        )
        self.comments.itemClicked.connect(self._on_comment_clicked)
        self.attachments.openPdfRequested.connect(self.openPdfAttachmentRequested)
        self.attachments.attachmentChanged.connect(self._on_attachment_changed)
        self.view.pageChanged.connect(self.thumbs.select_page)
        self.thumbs.orderChanged.connect(self._on_order_changed)

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
        self.side.setTabText(2, f"Comentarios ({total_c})" if total_c else "Comentarios")
        total_att = self.attachments.count()
        self.side.setTabText(3, f"Adjuntos ({total_att})" if total_att else "Adjuntos")
        if not has_bm and self.side.currentIndex() == 1:
            self.side.setCurrentIndex(0)

    # --------------------------------------------------------------- edición
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def run_edit(self, fn, select: list[int] | None = None, goto: int | None = None):
        """Aplica `fn(doc)` guardando una copia para deshacer. Si falla, restaura el documento."""
        snapshot = self.doc.tobytes()
        try:
            fn(self.doc)
        except Exception:
            self._load_bytes(snapshot)
            self.view.reload(self.doc)
            raise
        self._undo.append(snapshot)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.modified = True
        self._refresh(select, goto)

    def undo(self):
        if self._undo:
            self._redo.append(self.doc.tobytes())
            self._load_bytes(self._undo.pop())
            self.modified = True
            self._refresh()

    def redo(self):
        if self._redo:
            self._undo.append(self.doc.tobytes())
            self._load_bytes(self._redo.pop())
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
        self.doc.close()
