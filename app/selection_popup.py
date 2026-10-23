"""Pastilla flotante de acciones rápidas al seleccionar texto (Copiar, Resaltar, Tachar)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor


class TextSelectionPopup(QFrame):
    """Mini-barra flotante que aparece junto al texto seleccionado."""

    copyRequested = Signal()
    highlightRequested = Signal()
    strikeoutRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("TextSelectionPopup")
        self.setStyleSheet("""
            QFrame#TextSelectionPopup {
                background-color: #ffffff;
                border: 1px solid #c8ccd0;
                border-radius: 6px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #202124;
                padding: 4px 8px;
                font-size: 8.5pt;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
            }
            QPushButton:pressed {
                background-color: #e8eaed;
                color: #1a73e8;
            }
        """)

        # Sombra sutil
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)

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
        layout.addWidget(self.btn_hl)
        layout.addWidget(self.btn_so)

        self.hide()

    def show_at(self, global_pos):
        self.adjustSize()
        parent = self.parentWidget()
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
