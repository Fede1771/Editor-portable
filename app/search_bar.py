"""Barra de búsqueda flotante moderna estilo navegador (Ctrl+F)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
)


class FloatingSearchBar(QFrame):
    """Barra flotante compacta para búsqueda dentro del documento."""

    findNext = Signal()
    findPrev = Signal()
    searchTextChanged = Signal(str)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("FloatingSearchBar")
        self.setStyleSheet("""
            QFrame#FloatingSearchBar {
                background-color: #ffffff;
                border: 1px solid #c0c4cc;
                border-radius: 6px;
                padding: 2px 4px;
            }
            QLineEdit {
                background: transparent;
                border: none;
                color: #202124;
                padding: 3px 6px;
                min-width: 170px;
                font-size: 9pt;
            }
            QLabel {
                color: #5f6368;
                padding: 0 4px;
                font-size: 8.5pt;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 3px;
                color: #3c4043;
                padding: 3px 6px;
                font-size: 9pt;
            }
            QToolButton:hover {
                background: #e8eaed;
            }
            QToolButton:pressed {
                background: #d2e3fc;
                color: #1a73e8;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Buscar en el PDF…")
        self.edit.textChanged.connect(self.searchTextChanged.emit)
        self.edit.returnPressed.connect(self.findNext.emit)

        self.lbl_count = QLabel("")
        self.lbl_count.setAlignment(Qt.AlignCenter)

        self.btn_prev = QToolButton()
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip("Buscar anterior (Shift+F3)")
        self.btn_prev.clicked.connect(self.findPrev.emit)

        self.btn_next = QToolButton()
        self.btn_next.setText("▼")
        self.btn_next.setToolTip("Buscar siguiente (F3 o Enter)")
        self.btn_next.clicked.connect(self.findNext.emit)

        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Cerrar búsqueda (Esc)")
        self.btn_close.clicked.connect(self.hide_bar)

        layout.addWidget(self.edit)
        layout.addWidget(self.lbl_count)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_close)

        self.hide()

    def show_and_focus(self, initial_text: str = ""):
        if initial_text:
            self.edit.setText(initial_text)
        self.show()
        self.raise_()
        self.edit.setFocus()
        self.edit.selectAll()

    def hide_bar(self):
        self.hide()
        self.closed.emit()

    def set_result_status(self, current: int, total: int):
        if total <= 0:
            self.lbl_count.setText("Sin resultados" if self.edit.text().strip() else "")
        else:
            self.lbl_count.setText(f"{current} de {total}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            event.accept()
        else:
            super().keyPressEvent(event)
