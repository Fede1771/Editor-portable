"""Pastilla flotante de acciones rápidas al seleccionar texto (Copiar, Resaltar, Tachar)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor
from .tools_panel import FlowLayout


class TextSelectionPopup(QFrame):
    """Mini-barra flotante que aparece junto al texto seleccionado."""

    copyRequested = Signal()
    highlightRequested = Signal()
    strikeoutRequested = Signal()
    editRequested = Signal()
    underlineRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("TextSelectionPopup")
        self.setStyleSheet("""
            QFrame#TextSelectionPopup {
                background-color: palette(window);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: palette(window-text);
                padding: 7px 10px;
                font-size: 9pt;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: palette(midlight);
            }
            QPushButton:pressed {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
        """)

        # Sombra sutil
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        layout = FlowLayout(self, margin=4, spacing=2)

        self.btn_copy = QPushButton("📋 Copiar")
        self.btn_copy.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_copy.setToolTip("Copiar texto al portapapeles (Ctrl+C)")
        self.btn_copy.clicked.connect(self._on_copy)

        self.btn_hl = QPushButton("🖍 Resaltar")
        self.btn_hl.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_hl.setToolTip("Resaltar texto en amarillo")
        self.btn_hl.clicked.connect(self._on_highlight)

        self.btn_so = QPushButton("̶S̶ Tachar")
        self.btn_so.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_so.setToolTip("Tachar texto en rojo")
        self.btn_so.clicked.connect(self._on_strikeout)

        layout.addWidget(self.btn_copy)
        self.btn_edit = QPushButton("Editar texto")
        self.btn_edit.setToolTip("Editar el texto seleccionado")
        self.btn_edit.clicked.connect(lambda: (self.hide(), self.editRequested.emit()))
        layout.addWidget(self.btn_edit)
        layout.addWidget(self.btn_hl)
        self.btn_ul = QPushButton("Subrayar")
        self.btn_ul.setToolTip("Subrayar la selección (Shift+U)")
        self.btn_ul.clicked.connect(lambda: (self.hide(), self.underlineRequested.emit()))
        layout.addWidget(self.btn_ul)
        layout.addWidget(self.btn_so)

        self.hide()

    def show_at(self, global_pos):
        parent = self.parentWidget()
        preferred = sum(self.layout().itemAt(i).sizeHint().width() + 2 for i in range(self.layout().count())) + 8
        width = min(preferred, max(150, parent.width() - 12)) if parent else preferred
        self.setFixedSize(width, self.layout().heightForWidth(width))
        if parent is not None:
            local_pos = parent.mapFromGlobal(global_pos)
            pw = max(self.width() + 12, parent.width())
            ph = max(self.height() + 12, parent.height())
            x = local_pos.x() - self.width() // 2
            y = local_pos.y() - self.height() - 8
            if y < 6:
                y = local_pos.y() + 20
            x = max(6, min(x, pw - self.width() - 6))
            y = max(6, min(y, ph - self.height() - 6))
            self.move(x, y)
        else:
            x = global_pos.x() - self.width() // 2
            y = global_pos.y() - self.height() - 8
            if y < 10:
                y = global_pos.y() + 20
            self.move(max(10, x), y)
        self.show()
        self.raise_()

    def _on_copy(self):
        self.hide()
        self.copyRequested.emit()

    def _on_highlight(self):
        self.hide()
        self.highlightRequested.emit()

    def _on_strikeout(self):
        self.hide()
        self.strikeoutRequested.emit()
