"""Diálogos de las operaciones de páginas."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPointF, QStandardPaths, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QSlider, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import operations as ops


class PageScopeBox(QGroupBox):
    """Selector 'Aplicar a': páginas seleccionadas, todas o un rango."""

    def __init__(self, parent=None):
        super().__init__("Aplicar a", parent)
        self.r_sel = QRadioButton("Páginas seleccionadas")
        self.r_all = QRadioButton("Todas las páginas")
        self.r_range = QRadioButton("Rango:")
        self.r_sel.setChecked(True)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("ej: 1-3, 5, 8-")
        self.range_edit.setEnabled(False)
        self.r_range.toggled.connect(self.range_edit.setEnabled)
        lay = QVBoxLayout(self)
        lay.addWidget(self.r_sel)
        lay.addWidget(self.r_all)
        row = QHBoxLayout()
        row.addWidget(self.r_range)
        row.addWidget(self.range_edit)
        lay.addLayout(row)

    def pages(self, total: int, selected: list[int]) -> list[int]:
        if self.r_all.isChecked():
            return list(range(total))
        if self.r_range.isChecked():
            return ops.parse_ranges(self.range_edit.text(), total)
        return sorted(set(selected))


class _BaseDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.outer = QVBoxLayout(self)
        self.form = QFormLayout()
        self.outer.addLayout(self.form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._try_accept)
        self.buttons.rejected.connect(self.reject)

    def finish(self):
        self.outer.addWidget(self.buttons)

    def _validate(self) -> bool:
        return True

    def _try_accept(self):
        try:
            if not self._validate():
                return
        except ValueError as exc:
            QMessageBox.warning(self, "Datos no válidos", str(exc))
            return
        self.accept()


class _ColorButton(QPushButton):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = color
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        self.setStyleSheet(f"background-color: {self.color.name()}; min-height: 22px;")
        self.setText(self.color.name().upper())

    def _pick(self):
        c = QColorDialog.getColor(self.color, self, "Elegir color")
        if c.isValid():
            self.color = c
            self._refresh()

    def rgb(self) -> tuple[float, float, float]:
        return (self.color.redF(), self.color.greenF(), self.color.blueF())


class CropDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Recortar páginas", parent)
        self.spins = {}
        for key, label in (("left", "Izquierda"), ("top", "Arriba"),
                           ("right", "Derecha"), ("bottom", "Abajo")):
            s = QDoubleSpinBox()
            s.setRange(0, 500)
            s.setDecimals(1)
            s.setSuffix(" mm")
            self.spins[key] = s
            self.form.addRow(f"Margen {label.lower()}:", s)
        self.scope = PageScopeBox()
        self.outer.addWidget(self.scope)
        self.finish()

    def margins_pt(self) -> dict[str, float]:
        return {k: s.value() * 72 / 25.4 for k, s in self.spins.items()}

    def _validate(self):
        if not any(s.value() > 0 for s in self.spins.values()):
            raise ValueError("Indicá al menos un margen mayor que cero.")
        return True


class WatermarkDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Marca de agua", parent)
        self.text = QLineEdit("CONFIDENCIAL")
        self.size = QSpinBox()
        self.size.setRange(8, 400)
        self.size.setValue(72)
        self.angle = QSpinBox()
        self.angle.setRange(-180, 180)
        self.angle.setValue(45)
        self.angle.setSuffix("°")
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(25)
        self.opacity_lbl = QLabel("25%")
        self.opacity.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v}%"))
        op_row = QHBoxLayout()
        op_row.addWidget(self.opacity)
        op_row.addWidget(self.opacity_lbl)
        self.color = _ColorButton(QColor(200, 0, 0))
        self.behind = QCheckBox("Colocar detrás del contenido")
        self.form.addRow("Texto:", self.text)
        self.form.addRow("Tamaño:", self.size)
        self.form.addRow("Ángulo:", self.angle)
        self.form.addRow("Opacidad:", op_row)
        self.form.addRow("Color:", self.color)
        self.form.addRow("", self.behind)
        self.scope = PageScopeBox()
        self.outer.addWidget(self.scope)
        self.finish()

    def _validate(self):
        if not self.text.text().strip():
            raise ValueError("Escribí el texto de la marca de agua.")
        return True


class HeaderFooterDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Encabezado, pie y numeración", parent)
        self.text = QLineEdit("Página {n} de {total}")
        self.position = QComboBox()
        self.position.addItems(list(ops.POSITIONS))
        self.position.setCurrentText("Abajo al centro")
        self.size = QSpinBox()
        self.size.setRange(6, 72)
        self.size.setValue(11)
        self.start = QSpinBox()
        self.start.setRange(0, 999999)
        self.start.setValue(1)
        self.digits = QSpinBox()
        self.digits.setRange(1, 12)
        self.digits.setValue(6)
        self.color = _ColorButton(QColor(0, 0, 0))
        self.form.addRow("Texto:", self.text)
        hint = QLabel("Variables: {n} número · {total} total de páginas · {bates} número Bates")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        self.form.addRow("", hint)
        self.form.addRow("Posición:", self.position)
        self.form.addRow("Tamaño:", self.size)
        self.form.addRow("Número inicial:", self.start)
        self.form.addRow("Dígitos Bates:", self.digits)
        self.form.addRow("Color:", self.color)
        self.scope = PageScopeBox()
        self.scope.r_all.setChecked(True)
        self.outer.addWidget(self.scope)
        self.finish()

    def _validate(self):
        if not self.text.text().strip():
            raise ValueError("Escribí el texto.")
        return True


class SplitDialog(_BaseDialog):
    MODES = ["Cada N páginas", "Por rangos", "Por marcadores de primer nivel"]

    def __init__(self, total: int, has_bookmarks: bool, parent=None):
        super().__init__("Dividir documento", parent)
        self.total = total
        self.mode = QComboBox()
        self.mode.addItems(self.MODES)
        if not has_bookmarks:
            self.mode.model().item(2).setEnabled(False)
        self.count = QSpinBox()
        self.count.setRange(1, max(1, total))
        self.count.setValue(1)
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("ej: 1-3; 4-6; 7-")
        self.folder = QLineEdit()
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.folder)
        row.addWidget(browse)
        self.form.addRow("Dividir:", self.mode)
        self.form.addRow("Páginas por parte:", self.count)
        self.form.addRow("Rangos:", self.ranges)
        self.form.addRow("Carpeta de salida:", row)
        self.mode.currentIndexChanged.connect(self._sync)
        self._sync()
        self.finish()

    def _sync(self):
        i = self.mode.currentIndex()
        self.count.setEnabled(i == 0)
        self.ranges.setEnabled(i == 1)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.folder.text())
        if d:
            self.folder.setText(d)

    def _validate(self):
        if not self.folder.text().strip():
            raise ValueError("Elegí una carpeta de salida.")
        if self.mode.currentIndex() == 1:
            for chunk in [c for c in self.ranges.text().replace("|", ";").split(";") if c.strip()]:
                ops.parse_ranges(chunk, self.total)
            if not self.ranges.text().strip():
                raise ValueError("Indicá los rangos (separá las partes con ';').")
        return True


class CombineDialog(_BaseDialog):
    """Lista ordenable de archivos para crear o combinar un PDF."""

    def __init__(self, files: list[str] | None = None, parent=None):
        super().__init__("Crear o combinar PDF desde archivos", parent)
        self.setMinimumSize(560, 460)
        from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem
        self._Item = QListWidgetItem
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.outer.insertWidget(0, QLabel("Archivos (PDF, imágenes, Word/Excel/PowerPoint, HTML o texto). "
                                         "Arrastrá para cambiar el orden:"))
        self.outer.insertWidget(1, self.list, 1)

        row = QHBoxLayout()
        for text, slot in (("Agregar…", self._add), ("Quitar", self._remove),
                           ("Subir", lambda: self._move(-1)), ("Bajar", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        self.outer.insertLayout(2, row)

        self.image_mode = QComboBox()
        for label in ops_image_modes():
            self.image_mode.addItem(label)
        self.bookmarks = QCheckBox("Crear un marcador por cada archivo")
        self.bookmarks.setChecked(True)
        self.form.addRow("Tamaño de página para imágenes:", self.image_mode)
        self.form.addRow("", self.bookmarks)
        self.finish()
        for f in files or []:
            self._append(f)

    def _append(self, path: str):
        from . import creation
        if creation.classify(path) is None:
            return
        item = self._Item(path)
        item.setToolTip(path)
        self.list.addItem(item)

    def _add(self):
        from . import creation
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(self, "Agregar archivos", docs, creation.file_filter())
        for p in paths:
            self._append(p)

    def _remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _move(self, direction: int):
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if direction < 0 and rows[0] == 0 or direction > 0 and rows[-1] == self.list.count() - 1:
            return
        for r in (rows if direction < 0 else reversed(rows)):
            item = self.list.takeItem(r)
            self.list.insertItem(r + direction, item)
            item.setSelected(True)

    def files(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def mode(self) -> str:
        from . import creation
        return creation.IMAGE_MODES[self.image_mode.currentText()]

    def _validate(self):
        if not self.files():
            raise ValueError("Agregá al menos un archivo.")
        return True


def ops_image_modes() -> list[str]:
    from . import creation
    return list(creation.IMAGE_MODES)



class TextEditDialog(_BaseDialog):
    """Diálogo para editar texto existente o insertar uno nuevo."""

    def __init__(
        self,
        default_text: str = "",
        fontsize: float = 12.0,
        fontname: str = "helv",
        color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        is_editing: bool = False,
        align: int = 0,
        parent=None,
    ):
        title = "Editar texto existente" if is_editing else "Insertar texto en el PDF"
        super().__init__(title, parent)
        self.setMinimumWidth(500)
        self.is_editing = is_editing
        from PySide6.QtWidgets import QLabel, QTextEdit, QDoubleSpinBox
        import pymupdf as fitz

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(default_text)
        self.text_edit.setPlaceholderText("Escribí el texto aquí...")
        self.text_edit.setMinimumHeight(120)

        # Parsear familia, negrita y cursiva a partir del código de fuente
        fn_l = (fontname or "helv").lower()
        if fn_l.startswith("co"):
            family = "cour"
        elif fn_l.startswith("ti"):
            family = "tiro"
        else:
            family = "helv"

        is_bold = fn_l in ("hebo", "hebi", "tibo", "tibi", "cobo", "cobi")
        is_italic = fn_l in ("heit", "hebi", "tiit", "tibi", "coit", "cobi")

        self.font_combo = QComboBox()
        self.font_combo.addItem("Helvetica (Sans-Serif / Arial)", "helv")
        self.font_combo.addItem("Times Roman (Serif)", "tiro")
        self.font_combo.addItem("Courier (Monoespaciada)", "cour")

        idx = self.font_combo.findData(family)
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)

        self.chk_bold = QCheckBox("Negrita")
        self.chk_bold.setChecked(is_bold)
        self.chk_italic = QCheckBox("Cursiva")
        self.chk_italic.setChecked(is_italic)

        font_row = QHBoxLayout()
        font_row.addWidget(self.font_combo, 2)
        font_row.addWidget(self.chk_bold, 1)
        font_row.addWidget(self.chk_italic, 1)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(4.0, 144.0)
        self.size_spin.setSingleStep(0.5)
        self.size_spin.setDecimals(1)
        self.size_spin.setValue(max(4.0, float(fontsize)))
        self.size_spin.setSuffix(" pt")

        qc = QColor.fromRgbF(
            max(0.0, min(1.0, color[0])),
            max(0.0, min(1.0, color[1])),
            max(0.0, min(1.0, color[2])),
        )
        self.color_btn = _ColorButton(qc)

        self.align_combo = QComboBox()
        self.align_combo.addItem("Izquierda", fitz.TEXT_ALIGN_LEFT)
        self.align_combo.addItem("Centrado", fitz.TEXT_ALIGN_CENTER)
        self.align_combo.addItem("Derecha", fitz.TEXT_ALIGN_RIGHT)

        align_idx = self.align_combo.findData(align)
        if align_idx >= 0:
            self.align_combo.setCurrentIndex(align_idx)

        self.form.addRow("Texto:", self.text_edit)
        self.form.addRow("Tipografía y estilo:", font_row)
        self.form.addRow("Tamaño:", self.size_spin)
        self.form.addRow("Color:", self.color_btn)
        self.form.addRow("Alineación:", self.align_combo)

        if is_editing:
            self.chk_autofit = QCheckBox("Ajustar automáticamente al recuadro (evita desbordes)")
            self.chk_autofit.setChecked(True)
            self.form.addRow("", self.chk_autofit)

            hint = QLabel("✨ Propiedades detectadas automáticamente (tipografía, estilo, tamaño, color y alineación).")
            hint.setStyleSheet("color: #2b7bb9; font-weight: 500;")
            hint.setWordWrap(True)
            self.form.addRow("", hint)
        else:
            self.chk_autofit = None

        self.finish()

    def get_values(self) -> tuple[str, str, float, tuple[float, float, float], bool, int]:
        family = self.font_combo.currentData() or "helv"
        b = self.chk_bold.isChecked()
        it = self.chk_italic.isChecked()
        if family == "tiro":
            font_code = "tibi" if (b and it) else ("tibo" if b else ("tiit" if it else "tiro"))
        elif family == "cour":
            font_code = "cobi" if (b and it) else ("cobo" if b else ("coit" if it else "cour"))
        else:
            font_code = "hebi" if (b and it) else ("hebo" if b else ("heit" if it else "helv"))

        autofit = self.chk_autofit.isChecked() if self.chk_autofit else False
        align = self.align_combo.currentData() if self.align_combo else 0
        return (
            self.text_edit.toPlainText(),
            font_code,
            float(self.size_spin.value()),
            self.color_btn.rgb(),
            autofit,
            align,
        )

    def _validate(self) -> bool:
        if not self.is_editing and not self.text_edit.toPlainText().strip():
            raise ValueError("El texto no puede estar vacío.")
        return True


AddTextDialog = TextEditDialog


class FindRedactDialog(_BaseDialog):
    """Buscar una palabra o frase y censurarla permanentemente."""

    def __init__(self, default_phrase: str = "", parent=None):
        super().__init__("Buscar y censurar (Redacción permanente)", parent)
        self.phrase_edit = QLineEdit(default_phrase)
        self.phrase_edit.setPlaceholderText("ej: Confidencial, DNI, etc.")
        self.color_btn = _ColorButton(QColor(0, 0, 0))
        self.scope = PageScopeBox()
        self.scope.r_all.setChecked(True)

        self.form.addRow("Palabra / frase a censurar:", self.phrase_edit)
        self.form.addRow("Color del bloque:", self.color_btn)
        self.outer.addWidget(self.scope)
        self.finish()

    def phrase(self) -> str:
        return self.phrase_edit.text().strip()

    def fill_color(self) -> tuple[float, float, float]:
        return self.color_btn.rgb()

    def _validate(self) -> bool:
        if not self.phrase():
            raise ValueError("Debes ingresar la palabra o frase a buscar.")
        return True


class AddLinkDialog(_BaseDialog):
    """Diálogo para agregar un enlace hipervínculo o salto de página."""

    def __init__(self, total_pages: int = 1, parent=None):
        super().__init__("Insertar enlace / vínculo", parent)
        self.r_url = QRadioButton("Enlace a página web (URL)")
        self.r_page = QRadioButton("Saltar a página del documento")
        self.r_url.setChecked(True)

        self.url_edit = QLineEdit("https://")
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, max(1, total_pages))
        self.page_spin.setValue(1)
        self.page_spin.setEnabled(False)

        self.r_url.toggled.connect(lambda on: self.url_edit.setEnabled(on))
        self.r_page.toggled.connect(lambda on: self.page_spin.setEnabled(on))

        self.form.addRow(self.r_url)
        self.form.addRow("Dirección URL:", self.url_edit)
        self.form.addRow(self.r_page)
        self.form.addRow("Página de destino:", self.page_spin)
        self.finish()

    def is_url(self) -> bool:
        return self.r_url.isChecked()

    def uri(self) -> str:
        return self.url_edit.text().strip()

    def target_page(self) -> int:
        return self.page_spin.value() - 1

    def _validate(self) -> bool:
        if self.is_url() and not self.uri():
            raise ValueError("Ingresá una dirección URL válida.")
        return True



class OcrDialog(_BaseDialog):
    """Diálogo para configurar el reconocimiento de texto (OCR)."""

    def __init__(self, parent=None):
        super().__init__("Reconocimiento de texto (OCR)", parent)
        from . import ocr
        self.lang_combo = QComboBox()
        langs = ocr.get_available_languages()
        for name, code in langs.items():
            self.lang_combo.addItem(name, code)
        spa_idx = self.lang_combo.findData("spa")
        if spa_idx >= 0:
            self.lang_combo.setCurrentIndex(spa_idx)

        self.dpi_combo = QComboBox()
        self.dpi_combo.addItem("Máxima precisión y nitidez (300 DPI)", 300)
        self.dpi_combo.addItem("Alta calidad (200 DPI)", 200)
        self.dpi_combo.addItem("Estándar (150 DPI)", 150)
        self.dpi_combo.setCurrentIndex(0)

        self.form.addRow("Idioma del documento:", self.lang_combo)
        self.form.addRow("Resolución de escaneo:", self.dpi_combo)

        self.scope = PageScopeBox()
        self.scope.r_all.setChecked(True)
        self.outer.addWidget(self.scope)
        self.finish()

    def language(self) -> str:
        return self.lang_combo.currentData()

    def dpi(self) -> int:
        return self.dpi_combo.currentData()


class ConvertImagesDialog(_BaseDialog):
    """Diálogo para exportar páginas a imágenes PNG o JPG."""

    def __init__(self, parent=None):
        super().__init__("Exportar páginas a imágenes", parent)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItem("PNG (Sin pérdida / Máxima nitidez)", "png")
        self.fmt_combo.addItem("JPEG (Comprimido / Menor peso)", "jpg")

        self.dpi_combo = QComboBox()
        self.dpi_combo.addItem("Pantalla (150 DPI)", 150)
        self.dpi_combo.addItem("Impresión estándar (200 DPI)", 200)
        self.dpi_combo.addItem("Alta definición (300 DPI)", 300)
        self.dpi_combo.setCurrentIndex(1)

        self.folder_edit = QLineEdit()
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.folder_edit)
        row.addWidget(browse_btn)

        self.form.addRow("Formato de imagen:", self.fmt_combo)
        self.form.addRow("Resolución:", self.dpi_combo)
        self.form.addRow("Carpeta de destino:", row)

        self.scope = PageScopeBox()
        self.scope.r_all.setChecked(True)
        self.outer.addWidget(self.scope)
        self.finish()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de destino")
        if d:
            self.folder_edit.setText(d)

    def format(self) -> str:
        return self.fmt_combo.currentData()

    def dpi(self) -> int:
        return self.dpi_combo.currentData()

    def folder(self) -> str:
        return self.folder_edit.text().strip()

    def _validate(self) -> bool:
        if not self.folder():
            raise ValueError("Debes elegir una carpeta de destino.")
        return True


class CompressPdfDialog(_BaseDialog):
    """Diálogo limpio y moderno de compresión con perfiles específicos para aseguradoras."""

    def __init__(self, current_doc_title: str = "", current_size_bytes: int = 0, parent=None):
        super().__init__("Comprimir y reducir tamaño de PDF", parent)
        self.setMinimumWidth(520)

        # Indicador de tamaño actual adaptativo
        if current_size_bytes > 0:
            if current_size_bytes >= 1024 * 1024:
                size_str = f"{current_size_bytes / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{current_size_bytes / 1024:.1f} KB"
            lbl_size = QLabel(f"Tamaño actual del documento: <b>{size_str}</b>")
            self.form.addRow(lbl_size)

        # Grupo de perfiles específicos de pólizas y siniestros
        grp_profiles = QGroupBox("Perfiles de compresión")
        grp_lay = QVBoxLayout(grp_profiles)
        grp_lay.setSpacing(8)

        self.btn_group = QButtonGroup(self)

        self.rb_standard = QRadioButton("📂 Archivo Digital Corporativo (Recomendado)")
        self.rb_standard.setStyleSheet("font-weight: bold;")
        self.lbl_standard_desc = QLabel("   Equilibrio óptimo para repositorios y gestión de siniestros (180 DPI · Calidad 80%).")
        self.lbl_standard_desc.setStyleSheet("font-size: 8.5pt;")

        self.rb_email = QRadioButton("📧 Envío por Correo / Póliza Ligera (< 5 MB)")
        self.rb_email.setStyleSheet("font-weight: bold;")
        self.lbl_email_desc = QLabel("   Compresión alta para enviar pólizas o certificados por email sin rebotar (130 DPI · Calidad 65%).")
        self.lbl_email_desc.setStyleSheet("font-size: 8.5pt;")

        self.rb_high = QRadioButton("⚖️ Legajo Pericial / Siniestros (Máxima Nitidez)")
        self.rb_high.setStyleSheet("font-weight: bold;")
        self.lbl_high_desc = QLabel("   Preserva al máximo detalles de fotos de daños periciales y firmas (300 DPI · Calidad 92%).")
        self.lbl_high_desc.setStyleSheet("font-size: 8.5pt;")

        self.rb_custom = QRadioButton("🛠️ Personalizado")
        self.rb_custom.setStyleSheet("font-weight: bold;")

        self.btn_group.addButton(self.rb_standard, 1)
        self.btn_group.addButton(self.rb_email, 2)
        self.btn_group.addButton(self.rb_high, 3)
        self.btn_group.addButton(self.rb_custom, 4)

        grp_lay.addWidget(self.rb_standard)
        grp_lay.addWidget(self.lbl_standard_desc)
        grp_lay.addWidget(self.rb_email)
        grp_lay.addWidget(self.lbl_email_desc)
        grp_lay.addWidget(self.rb_high)
        grp_lay.addWidget(self.lbl_high_desc)
        grp_lay.addWidget(self.rb_custom)

        self.rb_standard.setChecked(True)
        self.form.addRow(grp_profiles)

        # Panel de ajustes personalizados (se muestra si rb_custom está seleccionado)
        self.custom_box = QWidget()
        custom_lay = QFormLayout(self.custom_box)
        custom_lay.setContentsMargins(15, 0, 15, 0)

        self.custom_quality = QSlider(Qt.Horizontal)
        self.custom_quality.setRange(40, 95)
        self.custom_quality.setValue(80)
        self.custom_q_lbl = QLabel("80%")
        self.custom_quality.valueChanged.connect(lambda v: self.custom_q_lbl.setText(f"{v}%"))
        row_q = QHBoxLayout()
        row_q.addWidget(self.custom_quality)
        row_q.addWidget(self.custom_q_lbl)
        custom_lay.addRow("Calidad JPEG:", row_q)

        self.custom_dpi = QComboBox()
        self.custom_dpi.addItem("96 DPI (Web ultra ligero)", 96)
        self.custom_dpi.addItem("130 DPI (Email / Pólizas)", 130)
        self.custom_dpi.addItem("150 DPI (Estándar oficina)", 150)
        self.custom_dpi.addItem("180 DPI (Archivo equilibrado)", 180)
        self.custom_dpi.addItem("200 DPI (Alta resolución)", 200)
        self.custom_dpi.addItem("300 DPI (Calidad pericial / Impresión)", 300)
        self.custom_dpi.setCurrentIndex(3)
        custom_lay.addRow("Resolución máx. imágenes:", self.custom_dpi)

        self.custom_box.setVisible(False)
        self.rb_custom.toggled.connect(self.custom_box.setVisible)
        self.form.addRow(self.custom_box)

        # Opciones adicionales de privacidad
        self.chk_sanitize = QCheckBox("🛡️ Eliminar metadatos confidenciales (autor, fecha y software de creación)")
        self.chk_sanitize.setChecked(True)
        self.form.addRow("", self.chk_sanitize)

        self.finish()

    def get_settings(self) -> dict:
        if self.rb_email.isChecked():
            return {
                "profile": "email",
                "compress_images": True,
                "quality": 65,
                "max_dpi": 130,
                "sanitize": self.chk_sanitize.isChecked(),
                "max_dim": 1300,
            }
        elif self.rb_high.isChecked():
            return {
                "profile": "high",
                "compress_images": True,
                "quality": 92,
                "max_dpi": 300,
                "sanitize": self.chk_sanitize.isChecked(),
                "max_dim": 3000,
            }
        elif self.rb_custom.isChecked():
            dpi = self.custom_dpi.currentData()
            return {
                "profile": "custom",
                "compress_images": True,
                "quality": self.custom_quality.value(),
                "max_dpi": dpi,
                "sanitize": self.chk_sanitize.isChecked(),
                "max_dim": int(dpi * 10),
            }
        else:
            return {
                "profile": "standard",
                "compress_images": True,
                "quality": 80,
                "max_dpi": 180,
                "sanitize": self.chk_sanitize.isChecked(),
                "max_dim": 1800,
            }

    # Compatibilidad con métodos anteriores
    def compress_images(self) -> bool:
        return True

    def image_quality(self) -> int:
        return self.get_settings()["quality"]

    def sanitize(self) -> bool:
        return self.chk_sanitize.isChecked()


OptimizeDialog = CompressPdfDialog


class AddNoteDialog(_BaseDialog):
    """Diálogo para ingresar una nota o comentario adhesivo."""

    def __init__(self, author="Usuario", parent=None):
        super().__init__("Agregar nota / comentario", parent)
        self.author_edit = QLineEdit(author)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Escribe tu comentario o nota aquí...")
        self.text_edit.setFixedHeight(120)

        self.form.addRow("Autor / Nombre:", self.author_edit)
        self.form.addRow("Comentario:", self.text_edit)
        self.finish()

    def author(self) -> str:
        return self.author_edit.text().strip() or "Usuario"

    def content(self) -> str:
        return self.text_edit.toPlainText().strip()

    def _validate(self) -> bool:
        if not self.content():
            raise ValueError("El comentario no puede estar vacío.")
        return True


class FillFormsDialog(_BaseDialog):
    """Diálogo interactivo para inspeccionar y rellenar campos de formulario (AcroForms)."""

    def __init__(self, fields: list[dict], parent=None):
        super().__init__("Completar campos de formulario", parent)
        self.setMinimumWidth(500)
        self.widgets_map: dict[str, Any] = {}

        if not fields:
            lbl_empty = QLabel("Este documento no contiene campos de formulario interactivos.")
            lbl_empty.setStyleSheet("color: #666; font-style: italic;")
            self.form.addRow(lbl_empty)
        else:
            for f in fields:
                fname = f["name"]
                ftype = f["type"]
                label_txt = f.get("label") or fname
                val = f.get("value")

                if ftype == "CheckBox":
                    chk = QCheckBox("Marcado")
                    chk.setChecked(bool(val) and val not in ("Off", "No", False, 0))
                    self.widgets_map[fname] = ("checkbox", chk)
                    self.form.addRow(f"{label_txt} (Pág {f['page']+1}):", chk)
                elif ftype == "Choice" and f.get("choices"):
                    combo = QComboBox()
                    for choice in f["choices"]:
                        combo.addItem(str(choice))
                    if val in f["choices"]:
                        combo.setCurrentText(str(val))
                    self.widgets_map[fname] = ("choice", combo)
                    self.form.addRow(f"{label_txt} (Pág {f['page']+1}):", combo)
                else:
                    line = QLineEdit(str(val or ""))
                    self.widgets_map[fname] = ("text", line)
                    self.form.addRow(f"{label_txt} (Pág {f['page']+1}):", line)

        self.finish()

    def values(self) -> dict[str, Any]:
        result = {}
        for fname, (ftype, widget) in self.widgets_map.items():
            if ftype == "checkbox":
                result[fname] = widget.isChecked()
            elif ftype == "choice":
                result[fname] = widget.currentText()
            else:
                result[fname] = widget.text().strip()
        return result


