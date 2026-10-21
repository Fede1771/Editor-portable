"""Visor de PDF: widget de desplazamiento con renderizado bajo demanda y herramientas de interacción."""
from __future__ import annotations

from collections import OrderedDict

import pymupdf as fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap, QKeySequence
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QToolTip

from .selection_popup import TextSelectionPopup

MARGIN = 16
GAP = 12
MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
CACHE_SIZE = 40

MODE_CONTINUOUS = "continuous"
MODE_SINGLE = "single"
MODE_TWO = "two"

FIT_NONE = "none"
FIT_WIDTH = "width"
FIT_PAGE = "page"

TOOL_PAN = "pan"
TOOL_SELECT = "select"
TOOL_TEXT = "text"
TOOL_REDACT = "redact"
TOOL_IMAGE = "image"
TOOL_LINK = "link"
TOOL_PEN = "pen"
TOOL_NOTE = "note"
TOOL_HIGHLIGHT = "highlight"
TOOL_UNDERLINE = "underline"
TOOL_STRIKEOUT = "strikeout"


class PdfView(QAbstractScrollArea):
    """Muestra un documento PyMuPDF con zoom, rotación, herramientas de selección y edición."""

    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    modeChanged = Signal(str)
    toolChanged = Signal(str)

    textRequested = Signal(int, object)      # (page_idx, fitz.Rect)
    redactRequested = Signal(int, object)    # (page_idx, fitz.Rect)
    imageRequested = Signal(int, object)     # (page_idx, fitz.Rect)
    linkRequested = Signal(int, object)      # (page_idx, fitz.Rect)
    penStrokeFinished = Signal(int, object)  # (page_idx, list[tuple[float, float]])
    noteRequested = Signal(int, object)      # (page_idx, fitz.Point)
    highlightRequested = Signal(int, object) # (page_idx, fitz.Rect)
    underlineRequested = Signal(int, object) # (page_idx, fitz.Rect)
    strikeoutRequested = Signal(int, object) # (page_idx, fitz.Rect)
    textSelected = Signal(str)               # Texto seleccionado copiado
    linkActivated = Signal(str, str)         # (uri, visible_text) enlace externo clickeado

    def __init__(self, doc: fitz.Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.page_count = doc.page_count
        self._sizes = [(p.rect.width, p.rect.height) for p in doc]

        self._zoom = 1.0
        self._fit = FIT_WIDTH
        self._mode = MODE_CONTINUOUS
        self._rotation = 0
        self._current = 0
        self._tool = TOOL_PAN

        self._rows: list[list[int]] = []
        self._row_rects: list[QRectF] = []      # rectángulo de cada fila (coords de contenido)
        self._page_rects: dict[int, QRectF] = {}
        self._content_h = 0.0
        self._content_w = 0.0

        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()

        self._hits: list[tuple[int, fitz.Rect]] = []
        self._hit_index = -1

        self._panning = False
        self._pan_start = QPointF()
        self._pan_last = QPointF()

        self._dragging = False
        self._drag_start = QPointF()
        self._drag_current = QPointF()
        self._selected_text = ""
        self._selection_page: int = -1
        self._selection_line_rects: list[fitz.Rect] = []
        self._hover_block: tuple[int, fitz.Rect] | None = None
        self._pen_stroke: list[tuple[float, float]] = []
        self._pen_page: int = -1
        self._annots_cache: dict[int, list] = {}
        self._blocks_cache: dict[int, list] = {}
        self._words_cache: dict[int, list] = {}
        self._links_cache: dict[int, list[dict]] = {}
        self._last_selection_target: tuple[int, fitz.Rect] | None = None

        self.popup = TextSelectionPopup(self.viewport())
        self.popup.copyRequested.connect(self._copy_selection)
        self.popup.highlightRequested.connect(self._highlight_selection)
        self.popup.strikeoutRequested.connect(self._strikeout_selection)

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setBackgroundRole(self.backgroundRole())
        self.viewport().setStyleSheet("background-color: #525659;")
        self._update_cursor()
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._relayout(keep_position=False)

    # ------------------------------------------------------------------ estado
    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def fit(self) -> str:
        return self._fit

    @property
    def rotation(self) -> int:
        return self._rotation

    @property
    def current_page(self) -> int:
        return self._current

    @property
    def tool(self) -> str:
        return self._tool

    def set_tool(self, tool: str):
        if tool != self._tool:
            self._tool = tool
            self._dragging = False
            self._hover_block = None
            self._selection_line_rects.clear()
            self._selection_page = -1
            self._selected_text = ""
            self.popup.hide()
            self._update_cursor()
            self.toolChanged.emit(tool)
            self.viewport().update()

    def _copy_selection(self):
        if self._selected_text:
            QApplication.clipboard().setText(self._selected_text)
            self.textSelected.emit(self._selected_text)
        self.popup.hide()

    def _highlight_selection(self):
        if self._selection_line_rects and self._selection_page >= 0:
            self.highlightRequested.emit(self._selection_page, list(self._selection_line_rects))
        elif self._last_selection_target:
            pno, rect = self._last_selection_target
            self.highlightRequested.emit(pno, [rect])
        self.popup.hide()

    def _strikeout_selection(self):
        if self._selection_line_rects and self._selection_page >= 0:
            self.strikeoutRequested.emit(self._selection_page, list(self._selection_line_rects))
        elif self._last_selection_target:
            pno, rect = self._last_selection_target
            self.strikeoutRequested.emit(pno, [rect])
        self.popup.hide()

    def _update_cursor(self):
        if self._tool == TOOL_PAN:
            self.viewport().setCursor(QCursor(Qt.OpenHandCursor))
        elif self._tool in (TOOL_SELECT, TOOL_HIGHLIGHT, TOOL_UNDERLINE, TOOL_STRIKEOUT):
            self.viewport().setCursor(QCursor(Qt.IBeamCursor))
        elif self._tool == TOOL_NOTE:
            self.viewport().setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.viewport().setCursor(QCursor(Qt.CrossCursor))

    # ------------------------------------------------------------- API pública
    def set_zoom(self, zoom: float, fit: str = FIT_NONE):
        self._fit = fit
        self._apply_zoom(zoom)

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def fit_width(self):
        self._fit = FIT_WIDTH
        self._relayout()

    def fit_page(self):
        self._fit = FIT_PAGE
        self._relayout()

    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        self._relayout(keep_position=False)
        self.goto_page(self._current)
        self.modeChanged.emit(mode)

    def rotate_view(self, delta: int):
        self._rotation = (self._rotation + delta) % 360
        self._relayout(keep_position=False)
        self.goto_page(self._current)

    def goto_page(self, index: int):
        index = max(0, min(self.page_count - 1, index))
        if self._mode == MODE_SINGLE:
            if index != self._current:
                self._current = index
                self._relayout(keep_position=False)
            self.verticalScrollBar().setValue(0)
        else:
            rect = self._page_rects.get(index)
            if rect is not None:
                self.verticalScrollBar().setValue(int(rect.top() - MARGIN))
        self._update_current()
        self.viewport().update()

    def scroll_to_page_rect(self, pno: int, rect: fitz.Rect):
        """Desplaza la vista hasta el área específica de una anotación o elemento."""
        self.goto_page(pno)
        prect = self._page_rects.get(pno)
        if prect is not None and rect is not None:
            mrect = self._map_rect(pno, rect)
            target_y = int(prect.top() + mrect.top() - 50)
            self.verticalScrollBar().setValue(max(0, target_y))

    def next_page(self):
        step = 2 if self._mode == MODE_TWO else 1
        self.goto_page(self._current + step)

    def prev_page(self):
        step = 2 if self._mode == MODE_TWO else 1
        self.goto_page(self._current - step)

    def reload(self, doc: fitz.Document | None = None):
        """Vuelve a leer el documento (tras modificarlo)."""
        if doc is not None:
            self.doc = doc
        self.page_count = self.doc.page_count
        self._sizes = [(p.rect.width, p.rect.height) for p in self.doc]
        self._cache.clear()
        self._annots_cache.clear()
        self._blocks_cache.clear()
        self._words_cache.clear()
        self._links_cache.clear()
        self._selection_line_rects.clear()
        self._selection_page = -1
        self._current = min(self._current, max(0, self.page_count - 1))
        self._relayout()

    # ------------------------------------------------------------- búsqueda
    def search(self, text: str) -> int:
        self._hits = []
        self._hit_index = -1
        text = text.strip()
        if text:
            for i in range(self.page_count):
                for rect in self.doc[i].search_for(text):
                    self._hits.append((i, rect))
        if self._hits:
            self._hit_index = 0
            self._show_hit()
        self.viewport().update()
        return len(self._hits)

    def clear_search(self):
        self._hits = []
        self._hit_index = -1
        self.viewport().update()

    def next_hit(self) -> tuple[int, int]:
        if self._hits:
            self._hit_index = (self._hit_index + 1) % len(self._hits)
            self._show_hit()
        return self._hit_index + 1, len(self._hits)

    def prev_hit(self) -> tuple[int, int]:
        if self._hits:
            self._hit_index = (self._hit_index - 1) % len(self._hits)
            self._show_hit()
        return self._hit_index + 1, len(self._hits)

    def _show_hit(self):
        page, rect = self._hits[self._hit_index]
        if self._mode == MODE_SINGLE and page != self._current:
            self._current = page
            self._relayout(keep_position=False)
        prect = self._page_rects.get(page)
        if prect is not None:
            hr = self._map_rect(page, rect).translated(prect.topLeft())
            vbar = self.verticalScrollBar()
            hbar = self.horizontalScrollBar()
            vh = self.viewport().height()
            vw = self.viewport().width()
            if not (vbar.value() + 20 < hr.top() and hr.bottom() < vbar.value() + vh - 20):
                vbar.setValue(int(hr.center().y() - vh / 2))
            if not (hbar.value() < hr.left() and hr.right() < hbar.value() + vw):
                hbar.setValue(int(hr.center().x() - vw / 2))
        self._update_current()
        self.viewport().update()

    # -------------------------------------------------------------- geometría
    def _eff_size(self, i: int) -> tuple[float, float]:
        w, h = self._sizes[i]
        if self._rotation in (90, 270):
            w, h = h, w
        return w, h

    def _apply_zoom(self, zoom: float):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if abs(zoom - self._zoom) < 1e-6:
            return
        self._zoom = zoom
        self._relayout()

    def _build_rows(self) -> list[list[int]]:
        n = self.page_count
        if n == 0:
            return []
        if self._mode == MODE_SINGLE:
            return [[self._current]]
        if self._mode == MODE_TWO:
            return [[i, i + 1] if i + 1 < n else [i] for i in range(0, n, 2)]
        return [[i] for i in range(n)]

    def _compute_fit_zoom(self) -> float:
        vw = max(50, self.viewport().width())
        vh = max(50, self.viewport().height())
        rows = self._build_rows()
        if not rows:
            return self._zoom
        max_row_w = max(sum(self._eff_size(i)[0] for i in row) for row in rows)
        max_row_gap = max((len(row) - 1) * GAP for row in rows)
        zw = (vw - 2 * MARGIN - max_row_gap) / max_row_w
        if self._fit == FIT_WIDTH:
            z = zw
        else:
            max_row_h = max(max(self._eff_size(i)[1] for i in row) for row in rows)
            zh = (vh - 2 * MARGIN) / max_row_h
            z = min(zw, zh)
        return max(MIN_ZOOM, min(MAX_ZOOM, z))

    def _relayout(self, keep_position: bool = True):
        vbar = self.verticalScrollBar()
        ratio = vbar.value() / self._content_h if (keep_position and self._content_h > 0) else 0.0
        old_zoom = self._zoom

        if self._fit != FIT_NONE:
            self._zoom = self._compute_fit_zoom()

        self._rows = self._build_rows()
        self._row_rects = []
        self._page_rects = {}

        vw = self.viewport().width()
        row_sizes = []
        for row in self._rows:
            w = sum(self._eff_size(i)[0] for i in row) * self._zoom + (len(row) - 1) * GAP
            h = max(self._eff_size(i)[1] for i in row) * self._zoom
            row_sizes.append((w, h))

        self._content_w = (max((w for w, _ in row_sizes), default=0) + 2 * MARGIN)
        total_w = max(self._content_w, vw)

        y = float(MARGIN)
        for row, (rw, rh) in zip(self._rows, row_sizes):
            x = (total_w - rw) / 2
            self._row_rects.append(QRectF(x, y, rw, rh))
            for i in row:
                w, h = self._eff_size(i)
                w *= self._zoom
                h *= self._zoom
                self._page_rects[i] = QRectF(x, y + (rh - h) / 2, w, h)
                x += w + GAP
            y += rh + GAP
        self._content_h = y - GAP + MARGIN if self._rows else 0.0

        hbar = self.horizontalScrollBar()
        vp = self.viewport().size()
        hbar.setRange(0, max(0, int(self._content_w - vp.width())))
        hbar.setPageStep(vp.width())
        vbar.setRange(0, max(0, int(self._content_h - vp.height())))
        vbar.setPageStep(vp.height())
        vbar.setSingleStep(40)
        hbar.setSingleStep(40)

        if keep_position and self._mode != MODE_SINGLE:
            vbar.setValue(int(ratio * self._content_h))

        self._update_current()
        self.viewport().update()
        if abs(old_zoom - self._zoom) > 1e-6:
            self.zoomChanged.emit(self._zoom)

    # --------------------------------------------------------- página actual
    def _update_current(self):
        if not self._rows:
            return
        if self._mode == MODE_SINGLE:
            new = self._current
        else:
            probe = self.verticalScrollBar().value() + self.viewport().height() / 3
            new = self._rows[-1][0]
            for row, rect in zip(self._rows, self._row_rects):
                if probe <= rect.bottom() + GAP / 2:
                    new = row[0]
                    break
        if new != self._current:
            self._current = new
        self.pageChanged.emit(self._current)

    def _on_scroll(self):
        self.popup.hide()
        self._update_current()
        self.viewport().update()

    # ------------------------------------------------------------ renderizado
    def _pixmap(self, i: int) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (i, round(self._zoom, 4), self._rotation, dpr)
        pix = self._cache.get(key)
        if pix is not None:
            self._cache.move_to_end(key)
            return pix
        scale = self._zoom * dpr
        matrix = fitz.Matrix(scale, scale).prerotate(self._rotation)
        pm = self.doc[i].get_pixmap(matrix=matrix, alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        self._cache[key] = pix
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return pix

    def _map_rect(self, i: int, rect: fitz.Rect) -> QRectF:
        """Convierte un rectángulo en coords de página al espacio de la página mostrada."""
        m = fitz.Matrix(self._zoom, self._zoom).prerotate(self._rotation)
        page_box = self.doc[i].rect * m
        r = rect * m
        return QRectF(r.x0 - page_box.x0, r.y0 - page_box.y0, r.width, r.height)

    def _map_point(self, i: int, pt: fitz.Point) -> QPointF:
        """Convierte un punto en coords de página al espacio de la página mostrada."""
        m = fitz.Matrix(self._zoom, self._zoom).prerotate(self._rotation)
        page_box = self.doc[i].rect * m
        p = pt * m
        return QPointF(p.x - page_box.x0, p.y - page_box.y0)

    def viewport_to_page_point(self, pt: QPointF) -> tuple[int | None, fitz.Point | None]:
        """Convierte un punto del viewport a coords absolutas de la página PDF."""
        dx = self.horizontalScrollBar().value()
        dy = self.verticalScrollBar().value()
        cpt = pt + QPointF(dx, dy)
        for pno, prect in self._page_rects.items():
            if prect.contains(cpt):
                rel_x = cpt.x() - prect.x()
                rel_y = cpt.y() - prect.y()
                m = fitz.Matrix(self._zoom, self._zoom).prerotate(self._rotation)
                page_box = self.doc[pno].rect * m
                inv_m = ~m
                pdf_pt = fitz.Point(rel_x + page_box.x0, rel_y + page_box.y0) * inv_m
                return pno, pdf_pt
        return None, None

    def viewport_to_page_rect(self, p1: QPointF, p2: QPointF) -> tuple[int | None, fitz.Rect | None]:
        """Convierte una región de arrastre del viewport a un fitz.Rect en la página PDF."""
        pno1, pt1 = self.viewport_to_page_point(p1)
        pno2, pt2 = self.viewport_to_page_point(p2)
        pno = pno1 if pno1 is not None else pno2
        if pno is None:
            return None, None
        pt1 = pt1 or pt2
        pt2 = pt2 or pt1
        rect = fitz.Rect(min(pt1.x, pt2.x), min(pt1.y, pt2.y), max(pt1.x, pt2.x), max(pt1.y, pt2.y))
        return pno, rect

    def _get_text_lines_in_rect(self, pno: int, rect: fitz.Rect) -> list[fitz.Rect]:
        """Obtiene los rectángulos individuales de las líneas de texto dentro del área."""
        if pno not in self._words_cache:
            try:
                self._words_cache[pno] = self.doc[pno].get_text("words")
            except Exception:
                self._words_cache[pno] = []
        words = self._words_cache.get(pno, [])
        selected_words = []
        for w in words:
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            if rect.intersects(w_rect):
                cx = (w[0] + w[2]) * 0.5
                cy = (w[1] + w[3]) * 0.5
                if rect.contains(fitz.Point(cx, cy)) or (rect & w_rect).get_area() >= 0.25 * w_rect.get_area():
                    selected_words.append(w)
        if not selected_words:
            return []
        lines_dict: dict[tuple[int, int], list] = {}
        for w in selected_words:
            lines_dict.setdefault((w[5], w[6]), []).append(w)
        sorted_lines = sorted(lines_dict.values(), key=lambda lw: (min(w[1] for w in lw), min(w[0] for w in lw)))
        res = []
        for lw in sorted_lines:
            res.append(fitz.Rect(min(w[0] for w in lw), min(w[1] for w in lw), max(w[2] for w in lw), max(w[3] for w in lw)))
        return res

    def _update_text_selection(self, start_pos: QPointF, current_pos: QPointF):
        """Calcula la selección de texto fluida ajustada a las líneas y palabras reales."""
        pno, sel_rect = self.viewport_to_page_rect(start_pos, current_pos)
        if pno is None or sel_rect is None or sel_rect.is_empty:
            self._selection_line_rects = []
            self._selection_page = -1
            self._selected_text = ""
            return

        if pno not in self._words_cache:
            try:
                self._words_cache[pno] = self.doc[pno].get_text("words")
            except Exception:
                self._words_cache[pno] = []
        words = self._words_cache.get(pno, [])

        selected_words = []
        for w in words:
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            if sel_rect.intersects(w_rect):
                cx = (w[0] + w[2]) * 0.5
                cy = (w[1] + w[3]) * 0.5
                if sel_rect.contains(fitz.Point(cx, cy)) or (sel_rect & w_rect).get_area() >= 0.25 * w_rect.get_area():
                    selected_words.append(w)

        if selected_words:
            lines_dict: dict[tuple[int, int], list] = {}
            for w in selected_words:
                lines_dict.setdefault((w[5], w[6]), []).append(w)

            sorted_lines = sorted(lines_dict.values(), key=lambda lw: (min(w[1] for w in lw), min(w[0] for w in lw)))
            line_rects = []
            text_lines = []
            for lw in sorted_lines:
                lw.sort(key=lambda w: (w[0], w[7]))
                line_rects.append(fitz.Rect(min(w[0] for w in lw), min(w[1] for w in lw), max(w[2] for w in lw), max(w[3] for w in lw)))
                text_lines.append(" ".join(w[4] for w in lw))

            self._selection_page = pno
            self._selection_line_rects = line_rects
            self._selected_text = "\n".join(text_lines).strip()
        else:
            self._selection_page = pno
            self._selection_line_rects = [sel_rect]
            try:
                self._selected_text = self.doc[pno].get_textbox(sel_rect).strip()
            except Exception:
                self._selected_text = ""

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        dx = -self.horizontalScrollBar().value()
        dy = -self.verticalScrollBar().value()
        view_rect = QRectF(self.viewport().rect())

        if self.page_count == 0:
            return

        hits_by_page: dict[int, list[tuple[int, fitz.Rect]]] = {}
        for idx, (p, r) in enumerate(self._hits):
            hits_by_page.setdefault(p, []).append((idx, r))

        for i, rect in self._page_rects.items():
            target = rect.translated(dx, dy)
            if not target.intersects(view_rect):
                continue
            painter.fillRect(target.translated(3, 3), QColor(0, 0, 0, 60))
            painter.drawPixmap(target.topLeft(), self._pixmap(i))
            painter.setPen(QPen(QColor(30, 30, 30), 1))
            painter.drawRect(target)
            for idx, r in hits_by_page.get(i, []):
                hr = self._map_rect(i, r).translated(target.topLeft())
                color = QColor(255, 140, 0, 130) if idx == self._hit_index else QColor(255, 235, 0, 110)
                painter.fillRect(hr, color)

            # Selección de texto natural nativa (estilo Acrobat / navegador)
            if self._selection_line_rects and self._selection_page == i:
                sel_color = QColor(0, 120, 215, 80)
                for sr in self._selection_line_rects:
                    vr = self._map_rect(i, sr).translated(target.topLeft())
                    painter.fillRect(vr, sel_color)

        # Resaltado al pasar el cursor sobre un bloque de texto existente
        if self._hover_block is not None and not self._dragging and self._tool == TOOL_TEXT:
            hpno, hrect = self._hover_block
            if hpno in self._page_rects:
                target_page = self._page_rects[hpno].translated(dx, dy)
                hr = self._map_rect(hpno, hrect).translated(target_page.topLeft())
                painter.fillRect(hr, QColor(0, 120, 215, 30))
                painter.setPen(QPen(QColor(0, 120, 215, 200), 1, Qt.DashLine))
                painter.drawRect(hr)

        # Dibujar arrastre activo de herramientas
        if self._dragging:
            x0 = min(self._drag_start.x(), self._drag_current.x())
            y0 = min(self._drag_start.y(), self._drag_current.y())
            w = abs(self._drag_start.x() - self._drag_current.x())
            h = abs(self._drag_start.y() - self._drag_current.y())
            drag_rect = QRectF(x0, y0, w, h)

            if self._tool == TOOL_SELECT:
                # El resaltado se dibuja directamente sobre el texto con _selection_line_rects
                pass
            elif self._tool == TOOL_REDACT:
                painter.fillRect(drag_rect, QColor(220, 20, 60, 90))
                painter.setPen(QPen(QColor(220, 20, 60), 2, Qt.SolidLine))
                painter.drawRect(drag_rect)
            elif self._tool == TOOL_TEXT:
                painter.fillRect(drag_rect, QColor(30, 144, 255, 50))
                painter.setPen(QPen(QColor(30, 144, 255), 1, Qt.DashLine))
                painter.drawRect(drag_rect)
            elif self._tool == TOOL_IMAGE:
                painter.fillRect(drag_rect, QColor(46, 139, 87, 50))
                painter.setPen(QPen(QColor(46, 139, 87), 1, Qt.DashLine))
                painter.drawRect(drag_rect)
            elif self._tool == TOOL_LINK:
                painter.fillRect(drag_rect, QColor(147, 112, 219, 50))
                painter.setPen(QPen(QColor(147, 112, 219), 1, Qt.DashLine))
                painter.drawRect(drag_rect)
            elif self._tool == TOOL_HIGHLIGHT:
                painter.fillRect(drag_rect, QColor(255, 235, 59, 110))
                painter.setPen(QPen(QColor(251, 192, 45), 1, Qt.DashLine))
                painter.drawRect(drag_rect)
            elif self._tool == TOOL_UNDERLINE:
                painter.fillRect(drag_rect, QColor(33, 150, 243, 60))
                painter.setPen(QPen(QColor(33, 150, 243), 2, Qt.SolidLine))
                painter.drawLine(drag_rect.bottomLeft(), drag_rect.bottomRight())
            elif self._tool == TOOL_STRIKEOUT:
                painter.fillRect(drag_rect, QColor(244, 67, 54, 60))
                painter.setPen(QPen(QColor(244, 67, 54), 2, Qt.SolidLine))
                mid_y = drag_rect.center().y()
                painter.drawLine(QPointF(drag_rect.left(), mid_y), QPointF(drag_rect.right(), mid_y))

        # Dibujar trazo en vivo para herramienta de tinta/lápiz (TOOL_PEN)
        if self._tool == TOOL_PEN and len(self._pen_stroke) > 1 and self._pen_page in self._page_rects:
            target_page = self._page_rects[self._pen_page].translated(dx, dy)
            pen_pen = QPen(QColor(0, 40, 160), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen_pen)
            for i in range(len(self._pen_stroke) - 1):
                p1 = self._map_point(self._pen_page, fitz.Point(self._pen_stroke[i])) + target_page.topLeft()
                p2 = self._map_point(self._pen_page, fitz.Point(self._pen_stroke[i + 1])) + target_page.topLeft()
                painter.drawLine(p1, p2)

        painter.end()

    # ---------------------------------------------------------------- eventos
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.set_zoom(self._zoom * (1.15 if delta > 0 else 1 / 1.15))
            event.accept()
            return
        if self._mode == MODE_SINGLE:
            vbar = self.verticalScrollBar()
            delta = event.angleDelta().y()
            if delta < 0 and vbar.value() >= vbar.maximum() and self._current < self.page_count - 1:
                self.goto_page(self._current + 1)
                event.accept()
                return
            if delta > 0 and vbar.value() <= vbar.minimum() and self._current > 0:
                self.goto_page(self._current - 1)
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                event.accept()
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        self.popup.hide()
        if event.button() == Qt.LeftButton:
            if self._tool == TOOL_PAN:
                self._panning = True
                self._pan_start = event.position()
                self._pan_last = event.position()
                self.viewport().setCursor(QCursor(Qt.ClosedHandCursor))
            elif self._tool == TOOL_PEN:
                self._dragging = True
                pno, pt = self.viewport_to_page_point(event.position())
                if pno is not None and pt is not None:
                    self._pen_page = pno
                    self._pen_stroke = [(pt.x, pt.y)]
                else:
                    self._pen_page = -1
                    self._pen_stroke = []
            else:
                self._dragging = True
                self._drag_start = event.position()
                self._drag_current = event.position()
                if self._tool == TOOL_SELECT:
                    self._selection_line_rects.clear()
                    self._selection_page = -1
                    self._selected_text = ""
                self.viewport().update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
        elif self._dragging:
            if self._tool == TOOL_PEN:
                pno, pt = self.viewport_to_page_point(event.position())
                if pno == self._pen_page and pt is not None:
                    self._pen_stroke.append((pt.x, pt.y))
            elif self._tool == TOOL_SELECT:
                self._drag_current = event.position()
                self._update_text_selection(self._drag_start, self._drag_current)
            else:
                self._drag_current = event.position()
            self.viewport().update()
        else:
            pno, pt = self.viewport_to_page_point(event.position())
            tip_shown = False
            if pno is not None and pt is not None:
                if pno not in self._annots_cache:
                    cached = []
                    try:
                        page = self.doc[pno]
                        for annot in page.annots():
                            info = annot.info or {}
                            t_type = annot.type[1] if isinstance(annot.type, tuple) else str(annot.type)
                            author = info.get("title", "").strip()
                            content = info.get("content", "").strip()
                            if not content and t_type in ("Highlight", "Underline", "StrikeOut"):
                                try:
                                    content = page.get_text("text", clip=annot.rect).strip()
                                except Exception:
                                    pass
                            cached.append((annot.rect, t_type, author, content))
                    except Exception:
                        pass
                    self._annots_cache[pno] = cached

                for r, t_type, author, content in self._annots_cache.get(pno, []):
                    if r.contains(pt):
                        tip_lines = [f"[{t_type}]"]
                        if author:
                            tip_lines.append(f"Autor: {author}")
                        if content:
                            tip_lines.append(content)
                        QToolTip.showText(event.globalPosition().toPoint(), "\n".join(tip_lines), self.viewport())
                        tip_shown = True
                        break

            if not tip_shown and self._tool != TOOL_TEXT:
                # Comprobar hipervínculos si la herramienta es navegación o selección
                if self._tool in (TOOL_PAN, TOOL_SELECT) and pno is not None and pt is not None:
                    if pno not in self._links_cache:
                        try:
                            self._links_cache[pno] = self.doc[pno].get_links()
                        except Exception:
                            self._links_cache[pno] = []
                    hover_link = None
                    for l in self._links_cache.get(pno, []):
                        if l.get("from") and fitz.Rect(l["from"]).contains(pt):
                            hover_link = l
                            break
                    if hover_link:
                        self.viewport().setCursor(QCursor(Qt.PointingHandCursor))
                        dest = hover_link.get("uri") or f"Ir a página {hover_link.get('page', 0) + 1}"
                        QToolTip.showText(event.globalPosition().toPoint(), f"🔗 {dest}", self.viewport())
                        tip_shown = True
                    else:
                        self._update_cursor()
                        QToolTip.hideText()
                else:
                    QToolTip.hideText()

            if self._tool == TOOL_TEXT:
                new_hover = None
                if pno is not None and pt is not None:
                    if pno not in self._blocks_cache:
                        try:
                            text_dict = self.doc[pno].get_text("dict")
                            spans = []
                            for b in text_dict.get("blocks", []):
                                for line in b.get("lines", []):
                                    for s in line.get("spans", []):
                                        if s.get("text", "").strip():
                                            spans.append(fitz.Rect(s["bbox"]))
                            rows = []
                            for r in sorted(spans, key=lambda sb: (sb.y0, sb.x0)):
                                placed = False
                                for i_row, row in enumerate(rows):
                                    v_overlap = max(0.0, min(row.y1, r.y1) - max(row.y0, r.y0))
                                    if v_overlap >= 0.4 * min(row.height, r.height):
                                        if r.x0 - row.x1 <= 45.0 and row.x0 - r.x1 <= 45.0:
                                            rows[i_row] = row | r
                                            placed = True
                                            break
                                if not placed:
                                    rows.append(fitz.Rect(r))
                            self._blocks_cache[pno] = rows
                        except Exception:
                            self._blocks_cache[pno] = []

                    for r in self._blocks_cache.get(pno, []):
                        if r.contains(pt):
                            new_hover = (pno, r)
                            break

                if new_hover != self._hover_block:
                    self._hover_block = new_hover
                    if new_hover:
                        self.viewport().setCursor(QCursor(Qt.IBeamCursor))
                    else:
                        self.viewport().setCursor(QCursor(Qt.CrossCursor))
                    self.viewport().update()
        super().mouseMoveEvent(event)

    def _check_link_at(self, pno: int, pt: fitz.Point) -> bool:
        """Comprueba y activa un hipervínculo interno o externo en las coordenadas indicadas."""
        if pno not in self._links_cache:
            try:
                self._links_cache[pno] = self.doc[pno].get_links()
            except Exception:
                self._links_cache[pno] = []
        for l in self._links_cache.get(pno, []):
            if l.get("from") and fitz.Rect(l["from"]).contains(pt):
                if l.get("kind") == fitz.LINK_GOTO:
                    self.goto_page(l.get("page", 0))
                    return True
                elif l.get("kind") == fitz.LINK_URI:
                    uri = l.get("uri", "")
                    if uri:
                        txt = ""
                        try:
                            txt = self.doc[pno].get_text("text", clip=l["from"]).strip()
                        except Exception:
                            pass
                        self.linkActivated.emit(uri, txt)
                        return True
        return False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._panning:
                self._panning = False
                self.viewport().setCursor(QCursor(Qt.OpenHandCursor))
                dist = (self._pan_start - event.position()).manhattanLength()
                if dist < 5:
                    pno, pt = self.viewport_to_page_point(event.position())
                    if pno is not None and pt is not None:
                        self._check_link_at(pno, pt)
            elif self._dragging:
                self._dragging = False
                if self._tool == TOOL_PEN:
                    if len(self._pen_stroke) > 1 and self._pen_page >= 0:
                        self.penStrokeFinished.emit(self._pen_page, list(self._pen_stroke))
                    self._pen_stroke = []
                    self._pen_page = -1
                    self.viewport().update()
                else:
                    pno, rect = self.viewport_to_page_rect(self._drag_start, self._drag_current)
                    self.viewport().update()

                    if pno is not None and rect is not None:
                        if self._tool == TOOL_SELECT:
                            dist = (self._drag_start - self._drag_current).manhattanLength()
                            if dist >= 4 and self._selected_text and self._selection_line_rects:
                                pno = self._selection_page
                                union_rect = fitz.Rect(
                                    min(r.x0 for r in self._selection_line_rects),
                                    min(r.y0 for r in self._selection_line_rects),
                                    max(r.x1 for r in self._selection_line_rects),
                                    max(r.y1 for r in self._selection_line_rects),
                                )
                                self._last_selection_target = (pno, union_rect)
                                QApplication.clipboard().setText(self._selected_text)
                                self.textSelected.emit(self._selected_text)
                                self.popup.show_at(event.globalPosition().toPoint())
                            else:
                                self._selection_line_rects.clear()
                                self._selection_page = -1
                                self._selected_text = ""
                                self.popup.hide()
                                pt = fitz.Point(rect.x0, rect.y0)
                                self._check_link_at(pno, pt)
                        elif self._tool == TOOL_TEXT:
                            self.textRequested.emit(pno, rect)
                        elif self._tool == TOOL_REDACT:
                            self.redactRequested.emit(pno, rect)
                        elif self._tool == TOOL_IMAGE:
                            self.imageRequested.emit(pno, rect)
                        elif self._tool == TOOL_LINK:
                            self.linkRequested.emit(pno, rect)
                        elif self._tool == TOOL_HIGHLIGHT:
                            line_rects = self._get_text_lines_in_rect(pno, rect)
                            self.highlightRequested.emit(pno, line_rects if line_rects else rect)
                        elif self._tool == TOOL_UNDERLINE:
                            line_rects = self._get_text_lines_in_rect(pno, rect)
                            self.underlineRequested.emit(pno, line_rects if line_rects else rect)
                        elif self._tool == TOOL_STRIKEOUT:
                            line_rects = self._get_text_lines_in_rect(pno, rect)
                            self.strikeoutRequested.emit(pno, line_rects if line_rects else rect)
                        elif self._tool == TOOL_NOTE:
                            self.noteRequested.emit(pno, fitz.Point(rect.x0, rect.y0))

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        vbar = self.verticalScrollBar()
        step = int(self.viewport().height() * 0.85)

        if key == Qt.Key_Escape:
            self._selection_line_rects.clear()
            self._selection_page = -1
            self._selected_text = ""
            self.popup.hide()
            self.viewport().update()
            event.accept()
        elif key in (Qt.Key_Right, Qt.Key_PageDown):
            if self._mode == MODE_CONTINUOUS:
                vbar.setValue(vbar.value() + step)
            else:
                self.next_page()
            event.accept()
        elif key in (Qt.Key_Left, Qt.Key_PageUp):
            if self._mode == MODE_CONTINUOUS:
                vbar.setValue(vbar.value() - step)
            else:
                self.prev_page()
            event.accept()
        elif key == Qt.Key_Space:
            if event.modifiers() & Qt.ShiftModifier:
                vbar.setValue(vbar.value() - step)
            else:
                vbar.setValue(vbar.value() + step)
            event.accept()
        elif key in (Qt.Key_Down, Qt.Key_J):
            vbar.setValue(vbar.value() + 50)
            event.accept()
        elif key in (Qt.Key_Up, Qt.Key_K):
            vbar.setValue(vbar.value() - 50)
            event.accept()
        elif key == Qt.Key_Home:
            self.goto_page(0)
            event.accept()
        elif key == Qt.Key_End:
            self.goto_page(self.page_count - 1)
            event.accept()
        elif event.matches(QKeySequence.Copy):
            if self._selected_text:
                QApplication.clipboard().setText(self._selected_text)
            event.accept()
        else:
            super().keyPressEvent(event)
