"""Ventana principal: barra de herramientas, menús, pestañas y operaciones de páginas."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDialog, QFileDialog, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QSizePolicy, QSpinBox, QStackedWidget,
    QTabWidget, QToolBar, QToolButton, QWidget,
)

from . import content_ops as cops
from . import conversion as conv
from . import creation
from . import ocr
from . import operations as ops
from . import optimizer as opt
from . import annotations as annot_mod
from . import forms as forms_mod
from .background import run_blocking
from .dialogs import (
    AddLinkDialog, AddNoteDialog, AddTextDialog, CombineDialog, ConvertImagesDialog,
    CropDialog, FillFormsDialog, FindRedactDialog, HeaderFooterDialog, OcrDialog,
    OptimizeDialog, SignatureDialog, SplitDialog, TextEditDialog, WatermarkDialog,
    get_signature_path,
)
from .doc_tab import DocTab
from .welcome import WelcomeWidget, add_recent_file, get_recent_files, clear_recent_files
from .viewer import (
    FIT_NONE, MODE_CONTINUOUS, MODE_SINGLE, MODE_TWO,
    TOOL_HIGHLIGHT, TOOL_IMAGE, TOOL_LINK, TOOL_NOTE, TOOL_PAN, TOOL_PEN,
    TOOL_REDACT, TOOL_SELECT, TOOL_SIGN, TOOL_STRIKEOUT, TOOL_TEXT, TOOL_UNDERLINE,
)

ZOOM_PRESETS = ["50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"]
PDF_FILTER = "Documentos PDF (*.pdf)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Editor PDF Portable")
        self.resize(1250, 820)
        self.setAcceptDrops(True)
        self._current_tool = TOOL_PAN

        icon_candidates = [
            Path(sys.executable).parent / "_internal" / "data" / "app_icon.png" if getattr(sys, "frozen", False) else None,
            Path(sys.executable).parent / "data" / "app_icon.png" if getattr(sys, "frozen", False) else None,
            Path(__file__).resolve().parent.parent / "data" / "app_icon.png",
            Path(__file__).resolve().parent / "data" / "app_icon.png",
        ]
        for p in icon_candidates:
            if p and p.exists():
                self.setWindowIcon(QIcon(str(p)))
                break

        self.stack = QStackedWidget()
        self.welcome = WelcomeWidget(self)
        self.welcome.openFileRequested.connect(self.open_dialog)
        self.welcome.openRecentRequested.connect(self.open_file)
        self.welcome.blankDocRequested.connect(self.create_blank)
        self.welcome.combineRequested.connect(lambda: self._create_from_dialog([]))

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self._build_actions()
        self._build_toolbar()
        self._build_menu()
        self.status_pages = QLabel("")
        self.status_msg = QLabel("Abrí un PDF con Ctrl+O o arrastralo a la ventana")
        self.statusBar().addWidget(self.status_msg, 1)
        self.statusBar().addPermanentWidget(self.status_pages)
        self._update_controls()

    # ---------------------------------------------------------------- acciones
    def _act(self, text, slot, shortcut=None, tip=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
            a.setToolTip(f"{text} ({shortcut})" if shortcut else tip)
        a.setCheckable(checkable)
        a.triggered.connect(lambda _checked=False: slot())
        return a

    def _build_actions(self):
        v = self._view_do
        self.a_open = self._act("Abrir…", self.open_dialog, "Ctrl+O", "Abrir un PDF")
        self.a_save = self._act("Guardar", self.save_current, "Ctrl+S")
        self.a_save_as = self._act("Guardar como…", self.save_as_current, "Ctrl+Shift+S")
        self.a_save_sanitized = self._act("Guardar copia anónima…", self.save_sanitized_current,
                                          tip="Guarda una copia despojada de metadatos, nombres de autor y scripts")
        self.a_print = self._act("Imprimir…", self.print_document, "Ctrl+P", "Imprimir el documento actual")
        self.a_close = self._act("Cerrar pestaña", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self.a_quit = self._act("Salir", self.close, "Ctrl+Q")

        # Crear PDF
        self.a_new_files = self._act("Crear PDF desde archivos…", self.create_from_files, "Ctrl+N",
                                     "PDF, imágenes, Word/Excel/PowerPoint, HTML o texto")
        self.a_combine = self._act("Combinar archivos…", lambda: self._create_from_dialog([]), "Ctrl+Shift+N",
                                   "Unir varios archivos en un solo PDF")
        self.a_clip = self._act("Crear PDF desde el portapapeles", self.create_from_clipboard)
        self.a_scan = self._act("Crear PDF desde el escáner…", self.create_from_scanner)
        self.a_blank_doc = self._act("Documento en blanco (A4)", self.create_blank)
        self.a_undo = self._act("Deshacer", lambda: self._tab_do("undo"), "Ctrl+Z")
        self.a_redo = self._act("Rehacer", lambda: self._tab_do("redo"), "Ctrl+Y")

        self.a_zoom_in = self._act("＋", lambda: v("zoom_in"), "Ctrl+=", "Acercar")
        self.a_zoom_out = self._act("－", lambda: v("zoom_out"), "Ctrl+-", "Alejar")
        self.a_fit_w = self._act("Ancho", lambda: v("fit_width"), "Ctrl+1", "Ajustar al ancho")
        self.a_fit_p = self._act("Página", lambda: v("fit_page"), "Ctrl+2", "Ajustar a la página")
        self.a_rot_l = self._act("⟲", lambda: v("rotate_view", -90), "Ctrl+Shift+-", "Rotar vista a la izquierda")
        self.a_rot_r = self._act("⟳", lambda: v("rotate_view", 90), "Ctrl+Shift+=", "Rotar vista a la derecha")
        self.a_prev = self._act("◀", lambda: v("prev_page"), None, "Página anterior")
        self.a_next = self._act("▶", lambda: v("next_page"), None, "Página siguiente")
        self.a_side = self._act("Panel lateral", self._toggle_side, "F4", "Mostrar u ocultar el panel lateral")
        self.a_find = self._act("🔍 Buscar…", self.show_find_bar, "Ctrl+F", "Buscar texto en el documento")
        self.a_find_next = self._act("Buscar siguiente", self._find_next, "F3", "Ir a la coincidencia siguiente")
        self.a_find_prev = self._act("Buscar anterior", self._find_prev, "Shift+F3", "Ir a la coincidencia anterior")

        # Organizar páginas
        self.a_insert = self._act("Insertar páginas desde PDF…", self.insert_pages)
        self.a_blank = self._act("Insertar página en blanco", self.insert_blank)
        self.a_replace = self._act("Reemplazar páginas…", self.replace_pages)
        self.a_extract = self._act("Extraer páginas…", self.extract_pages)
        self.a_delete = self._act("Eliminar páginas", self.delete_pages, "Delete")
        self.a_delete.setShortcutContext(Qt.WidgetShortcut)
        self.a_dup = self._act("Duplicar páginas", self.duplicate_pages)
        self.a_pg_rot_l = self._act("Rotar páginas a la izquierda", lambda: self.rotate_pages(-90), "Ctrl+Shift+Left")
        self.a_pg_rot_r = self._act("Rotar páginas a la derecha", lambda: self.rotate_pages(90), "Ctrl+Shift+Right")
        self.a_move_up = self._act("Mover páginas hacia arriba", lambda: self.move_pages(-1), "Alt+Up")
        self.a_move_down = self._act("Mover páginas hacia abajo", lambda: self.move_pages(1), "Alt+Down")
        self.a_split = self._act("Dividir documento…", self.split_document)
        self.a_crop = self._act("Recortar páginas…", self.crop_pages)
        self.a_watermark = self._act("Marca de agua…", self.watermark)
        self.a_background = self._act("Color de fondo…", self.background)
        self.a_header = self._act("Encabezado, pie y numeración…", self.header_footer)

        # Herramientas de interacción, anotación y edición de contenido
        self.a_tool_pan = self._act("🖐 Mano", lambda: self._set_active_tool(TOOL_PAN), "H", "Desplazar con la mano", checkable=True)
        self.a_tool_select = self._act("🔤 Seleccionar", lambda: self._set_active_tool(TOOL_SELECT), "V", "Seleccionar y copiar texto", checkable=True)
        self.a_tool_text = self._act("✍ Texto", lambda: self._set_active_tool(TOOL_TEXT), "T", "Insertar cuadro de texto", checkable=True)
        self.a_tool_redact = self._act("⬛ Censurar", lambda: self._set_active_tool(TOOL_REDACT), "R", "Censurar / Redactar permanentemente", checkable=True)
        self.a_tool_image = self._act("🖼 Imagen", lambda: self._set_active_tool(TOOL_IMAGE), "I", "Insertar imagen en la página", checkable=True)
        self.a_tool_link = self._act("🔗 Enlace", lambda: self._set_active_tool(TOOL_LINK), "L", "Insertar enlace web o salto de página", checkable=True)
        self.a_tool_pen = self._act("✏ Lápiz", lambda: self._set_active_tool(TOOL_PEN), "P", "Dibujar a mano alzada", checkable=True)
        self.a_tool_highlight = self._act("🖍 Resaltar", lambda: self._set_active_tool(TOOL_HIGHLIGHT), "Shift+H", "Resaltar texto o área", checkable=True)
        self.a_tool_underline = self._act("⎁ Subrayar", lambda: self._set_active_tool(TOOL_UNDERLINE), "Shift+U", "Subrayar texto", checkable=True)
        self.a_tool_strikeout = self._act("̶S̶ Tachar", lambda: self._set_active_tool(TOOL_STRIKEOUT), "Shift+K", "Tachar texto", checkable=True)
        self.a_tool_note = self._act("💬 Nota", lambda: self._set_active_tool(TOOL_NOTE), "N", "Agregar nota adhesiva o comentario", checkable=True)
        self.a_tool_sign = self._act("🖋️ Firmar", self._activate_sign_tool, "Shift+F", "Estampar firma manuscrita personal en el documento", checkable=True)
        self.a_config_sign = self._act("Configurar firma personal…", self.configure_signature, None, "Dibujar o cargar imagen de firma manuscrita")

        self.a_fill_forms = self._act("Completar campos de formulario…", self.fill_form_fields, None, "Inspeccionar y editar campos de formulario (AcroForms)")
        self.a_flatten_forms = self._act("Aplanar formulario (Flatten)…", self.flatten_form_fields, None, "Convertir campos interactivos en contenido estático fijo")

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        for a in (
            self.a_tool_pan, self.a_tool_select, self.a_tool_text, self.a_tool_redact,
            self.a_tool_image, self.a_tool_sign, self.a_tool_link, self.a_tool_pen, self.a_tool_highlight,
            self.a_tool_underline, self.a_tool_strikeout, self.a_tool_note,
        ):
            self.tool_group.addAction(a)
        self.a_tool_pan.setChecked(True)

        self.a_find_redact = self._act("Buscar y censurar…", self.find_and_redact, None, "Buscar texto y censurarlo en todo el documento")
        self.a_extract_imgs = self._act("Extraer todas las imágenes…", self.extract_all_images, None, "Guardar las imágenes incrustadas a una carpeta")

        # Exportar / Convertir (Fase 6)
        self.a_export_word = self._act("Microsoft Word (.docx)…", self.export_to_word, None, "Exportar PDF a documento Word")
        self.a_export_excel = self._act("Microsoft Excel (.xlsx)…", self.export_to_excel, None, "Extraer tablas a hoja de cálculo Excel")
        self.a_export_images = self._act("Páginas a imágenes (PNG/JPEG)…", self.export_to_images, None, "Exportar páginas como imágenes de alta resolución")
        self.a_export_text = self._act("Texto plano (.txt)…", self.export_to_text, None, "Exportar todo el texto plano")
        self.a_export_html = self._act("Página web (.html)…", self.export_to_html, None, "Exportar como página HTML")

        # OCR y Optimización (Fases 5 y 10)
        self.a_ocr = self._act("Reconocer texto con OCR…", self.run_ocr, None, "Convertir documento escaneado a PDF con texto buscable")
        self.a_optimize = self._act("Optimizar y reducir tamaño…", self.optimize_document, None, "Comprimir imágenes y reducir el peso del archivo")
        self.a_attachments = self._act("Archivos adjuntos…", self.show_attachments, "Ctrl+Shift+A", "Ver y gestionar los archivos adjuntos incrustados en el PDF")

        self.utility_actions = [
            self.a_export_word, self.a_export_excel, self.a_export_images,
            self.a_export_text, self.a_export_html, self.a_ocr, self.a_optimize,
            self.a_fill_forms, self.a_flatten_forms, self.a_attachments,
        ]

        self.tool_actions = [
            self.a_tool_pan, self.a_tool_select, self.a_tool_text, self.a_tool_redact,
            self.a_tool_image, self.a_tool_link, self.a_tool_pen,
            self.a_tool_highlight, self.a_tool_underline, self.a_tool_strikeout, self.a_tool_note,
            self.a_find_redact, self.a_extract_imgs,
        ]

        self.page_actions = [
            self.a_insert, self.a_blank, self.a_replace, self.a_extract, self.a_delete, self.a_dup,
            self.a_pg_rot_l, self.a_pg_rot_r, self.a_move_up, self.a_move_down, self.a_split,
            self.a_crop, self.a_watermark, self.a_background, self.a_header,
        ]

    def _build_toolbar(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.a_open)
        tb.addAction(self.a_save)
        tb.addAction(self.a_print)
        tb.addSeparator()
        tb.addAction(self.a_prev)
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.valueChanged.connect(lambda val: self._view_do("goto_page", val - 1))
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        tb.addWidget(self.page_total)
        tb.addAction(self.a_next)
        tb.addSeparator()
        tb.addAction(self.a_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.addItems(ZOOM_PRESETS)
        self.zoom_combo.setMinimumWidth(80)
        self.zoom_combo.activated.connect(self._zoom_from_combo)
        self.zoom_combo.lineEdit().editingFinished.connect(self._zoom_from_combo)
        tb.addWidget(self.zoom_combo)
        tb.addAction(self.a_zoom_in)
        tb.addAction(self.a_fit_w)
        tb.addSeparator()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Continuo", MODE_CONTINUOUS)
        self.mode_combo.addItem("Una página", MODE_SINGLE)
        self.mode_combo.addItem("Dos páginas", MODE_TWO)
        self.mode_combo.activated.connect(
            lambda _i: self._view_do("set_mode", self.mode_combo.currentData())
        )
        tb.addWidget(self.mode_combo)
        tb.addSeparator()
        tb.addAction(self.a_tool_pan)
        tb.addAction(self.a_tool_select)
        tb.addAction(self.a_tool_text)
        tb.addAction(self.a_tool_redact)
        tb.addAction(self.a_tool_image)
        tb.addAction(self.a_tool_sign)

        btn_annot = QToolButton()
        btn_annot.setText("🖍 Anotar ▾")
        btn_annot.setToolTip("Más herramientas de dibujo y anotación")
        btn_annot.setPopupMode(QToolButton.InstantPopup)
        menu_annot = QMenu(btn_annot)
        menu_annot.addAction(self.a_tool_highlight)
        menu_annot.addAction(self.a_tool_underline)
        menu_annot.addAction(self.a_tool_strikeout)
        menu_annot.addAction(self.a_tool_pen)
        menu_annot.addAction(self.a_tool_note)
        menu_annot.addAction(self.a_tool_link)
        btn_annot.setMenu(menu_annot)
        tb.addWidget(btn_annot)

        tb.addSeparator()
        tb.addAction(self.a_side)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        tb.addAction(self.a_find)

    def _build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        m.addAction(self.a_open)
        self.menu_recents = m.addMenu("Abrir &recientes")
        self._update_recent_menu()
        sub = m.addMenu("&Crear PDF")
        for a in (self.a_new_files, self.a_combine, self.a_clip, self.a_scan, self.a_blank_doc):
            sub.addAction(a)
        sub_export = m.addMenu("&Exportar / Convertir a…")
        for a in (self.a_export_word, self.a_export_excel, self.a_export_images, self.a_export_text, self.a_export_html):
            sub_export.addAction(a)
        m.addSeparator()
        for a in (self.a_save, self.a_save_as, self.a_save_sanitized, self.a_print, self.a_close):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_quit)

        m = mb.addMenu("&Edición")
        m.addAction(self.a_undo)
        m.addAction(self.a_redo)
        m.addSeparator()
        m.addAction(self.a_find)
        m.addAction(self.a_find_next)
        m.addAction(self.a_find_prev)
        m.addSeparator()
        m.addAction(self.a_tool_select)
        m.addAction(self.a_tool_text)
        m.addAction(self.a_tool_redact)
        m.addAction(self.a_find_redact)
        m.addSeparator()
        m.addAction(self.a_tool_image)
        m.addAction(self.a_extract_imgs)
        m.addAction(self.a_tool_link)

        m = mb.addMenu("&Ver")
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_fit_w, self.a_fit_p):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_rot_l)
        m.addAction(self.a_rot_r)
        m.addSeparator()
        m.addAction(self.a_side)

        m = mb.addMenu("&Páginas")
        self._fill_pages_menu(m, full=True)

        m = mb.addMenu("&Herramientas")
        m.addAction(self.a_ocr)
        m.addAction(self.a_optimize)
        m.addAction(self.a_attachments)
        m.addSeparator()
        m.addAction(self.a_tool_sign)
        m.addAction(self.a_config_sign)
        m.addSeparator()
        m.addAction(self.a_find_redact)
        m.addAction(self.a_extract_imgs)

        m = mb.addMenu("&Anotaciones")
        m.addAction(self.a_tool_pen)
        m.addSeparator()
        m.addAction(self.a_tool_highlight)
        m.addAction(self.a_tool_underline)
        m.addAction(self.a_tool_strikeout)
        m.addAction(self.a_tool_note)

        m = mb.addMenu("&Formularios")
        m.addAction(self.a_fill_forms)
        m.addAction(self.a_flatten_forms)

        # Atajos válidos aunque el menú no tenga el foco
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_fit_w, self.a_fit_p, self.a_rot_l,
                  self.a_rot_r, self.a_side, self.a_find, self.a_find_next, self.a_find_prev,
                  self.a_open, self.a_save, self.a_save_as, self.a_close, self.a_quit,
                  self.a_new_files, self.a_combine,
                  self.a_undo, self.a_redo, self.a_pg_rot_l, self.a_pg_rot_r,
                  self.a_move_up, self.a_move_down,
                  self.a_tool_pan, self.a_tool_select, self.a_tool_text,
                  self.a_tool_redact, self.a_tool_image, self.a_tool_link,
                  self.a_tool_pen, self.a_tool_highlight, self.a_tool_underline,
                  self.a_tool_strikeout, self.a_tool_note, self.a_tool_sign):
            self.addAction(a)

    def _fill_pages_menu(self, m: QMenu, full: bool):
        m.addAction(self.a_insert)
        m.addAction(self.a_blank)
        m.addAction(self.a_replace)
        m.addAction(self.a_extract)
        m.addAction(self.a_dup)
        m.addAction(self.a_delete)
        m.addSeparator()
        m.addAction(self.a_pg_rot_l)
        m.addAction(self.a_pg_rot_r)
        m.addAction(self.a_move_up)
        m.addAction(self.a_move_down)
        if full:
            m.addSeparator()
            m.addAction(self.a_split)
            m.addAction(self.a_crop)
            m.addSeparator()
            m.addAction(self.a_watermark)
            m.addAction(self.a_background)
            m.addAction(self.a_header)

    def _thumb_menu(self, tab: DocTab, pos):
        menu = QMenu(self)
        self._fill_pages_menu(menu, full=False)
        menu.exec(tab.thumbs.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- documentos
    def current_tab(self) -> DocTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocTab) else None

    def _view_do(self, method: str, *args):
        tab = self.current_tab()
        if tab is not None:
            getattr(tab.view, method)(*args)

    def _tab_do(self, method: str):
        tab = self.current_tab()
        if tab is not None:
            getattr(tab, method)()

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Abrir PDF", "", f"{PDF_FILTER};;Todos los archivos (*)")
        for p in paths:
            self.open_file(p)

    def open_file(self, path: str):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, DocTab) and w.path == path:
                self.tabs.setCurrentIndex(i)
                return
        save_as_only = False
        try:
            if path.lower().endswith(".pdf"):
                with open(path, "rb") as fh:       # en memoria: se puede guardar sobre el mismo archivo
                    doc = fitz.open("pdf", fh.read())
            else:
                src = fitz.open(path)
                if src.is_pdf:
                    doc = src
                else:
                    doc = fitz.open("pdf", src.convert_to_pdf())
                    src.close()
                    save_as_only = True
            if doc.needs_pass:
                pwd, ok = QInputDialog.getText(self, "PDF protegido", "Contraseña:", QLineEdit.Password)
                if not ok or not doc.authenticate(pwd):
                    doc.close()
                    QMessageBox.warning(self, "Error", "Contraseña incorrecta o cancelada.")
                    return
            if doc.page_count == 0:
                raise ValueError("El documento no tiene páginas.")
            self._add_tab(path, doc, save_as_only=save_as_only)
            if path and os.path.exists(path):
                add_recent_file(path)
                self._update_recent_menu()
                self.welcome.refresh_recents()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo abrir", f"{path}\n\n{exc}")
            return

    def _add_tab(self, path: str, doc: fitz.Document, save_as_only: bool = False,
                 modified: bool = False, suggested: str = "documento.pdf"):
        tab = DocTab(path, doc)
        tab.save_as_only = save_as_only
        tab.modified = modified
        tab.suggested = suggested
        tab.view.pageChanged.connect(lambda _p, t=tab: self._sync_if_current(t))
        tab.view.zoomChanged.connect(lambda _z, t=tab: self._sync_if_current(t))
        tab.view.textRequested.connect(lambda pno, rect, t=tab: self._on_text_requested(t, pno, rect))
        tab.view.editBlockRequested.connect(lambda pno, rect, t=tab: self._on_text_requested(t, pno, rect))
        tab.view.signatureRequested.connect(lambda pno, pt, t=tab: self._on_signature_requested(t, pno, pt))
        tab.view.redactRequested.connect(lambda pno, rect, t=tab: self._on_redact_requested(t, pno, rect))
        tab.view.imageRequested.connect(lambda pno, rect, t=tab: self._on_image_requested(t, pno, rect))
        tab.view.linkRequested.connect(lambda pno, rect, t=tab: self._on_link_requested(t, pno, rect))
        tab.view.penStrokeFinished.connect(lambda pno, stroke, t=tab: self._on_pen_stroke(t, pno, stroke))
        tab.view.noteRequested.connect(lambda pno, pt, t=tab: self._on_note_requested(t, pno, pt))
        tab.view.highlightRequested.connect(lambda pno, rect, t=tab: self._on_highlight_requested(t, pno, rect))
        tab.view.underlineRequested.connect(lambda pno, rect, t=tab: self._on_underline_requested(t, pno, rect))
        tab.view.strikeoutRequested.connect(lambda pno, rect, t=tab: self._on_strikeout_requested(t, pno, rect))
        tab.view.linkActivated.connect(self._on_link_activated)
        tab.view.textSelected.connect(lambda txt: self.status_msg.setText(f"Texto copiado ({len(txt)} caracteres) al portapapeles."))
        tab.view.set_tool(self._current_tool)
        tab.edited.connect(lambda t=tab: self._on_edited(t))
        tab.thumbs.addAction(self.a_delete)
        tab.thumbs.setContextMenuPolicy(Qt.CustomContextMenu)
        tab.thumbs.customContextMenuRequested.connect(lambda pos, t=tab: t._on_thumb_context_menu(pos))
        tab.openPdfAttachmentRequested.connect(self._open_attached_pdf)
        idx = self.tabs.addTab(tab, tab.title)
        self.tabs.setTabToolTip(idx, path)
        self.tabs.setCurrentIndex(idx)
        self.stack.setCurrentIndex(1)

        total_att = tab.attachments.count()
        if total_att > 0:
            self.status_msg.setText(f"📎 Este documento contiene {total_att} archivo(s) adjunto(s). Visibles en la pestaña 'Adjuntos' del panel lateral.")
            tab.side.setCurrentIndex(3)

        self._update_controls()

    def show_attachments(self):
        tab = self.current_tab()
        if not tab:
            return
        if not tab.side.isVisible():
            tab.side.setVisible(True)
        tab.side.setCurrentIndex(3)

    def _open_attached_pdf(self, pdf_bytes: bytes, filename: str):
        try:
            doc = fitz.open("pdf", pdf_bytes)
            self._add_tab("", doc, save_as_only=True, suggested=filename)
            self.status_msg.setText(f"Archivo adjunto '{filename}' abierto en nueva pestaña.")
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir adjunto", str(exc))

    def _confirm_close(self, tab: DocTab) -> bool:
        """Devuelve False si el usuario cancela el cierre."""
        if not tab.modified:
            return True
        r = QMessageBox.question(
            self, "Cambios sin guardar", f"¿Guardar los cambios en «{os.path.basename(tab.path) or 'Sin título'}»?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self._save_tab(tab)
        return True

    def close_tab(self, index: int) -> bool:
        if index < 0:
            return True
        w = self.tabs.widget(index)
        if isinstance(w, DocTab) and not self._confirm_close(w):
            return False
        self.tabs.removeTab(index)
        if isinstance(w, DocTab):
            w.close_document()
        w.deleteLater()
        self._update_controls()
        return True

    def _on_tab_changed(self, _index):
        self._update_controls()

    def _sync_if_current(self, tab: DocTab):
        if tab is self.current_tab():
            self._update_controls()

    def _on_edited(self, tab: DocTab):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.setTabText(idx, tab.title)
            self.tabs.setTabToolTip(idx, tab.path)
        if tab is self.current_tab():
            self._update_controls()

    # ---------------------------------------------------------------- guardar
    def _save_tab(self, tab: DocTab) -> bool:
        if tab.save_as_only or not tab.path:
            return self._save_tab_as(tab)
        try:
            tab.save()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self.status_msg.setText(f"Guardado: {tab.path}")
        return True

    def _save_tab_as(self, tab: DocTab) -> bool:
        base = os.path.splitext(tab.path)[0] + ".pdf" if tab.path else tab.suggested
        path, _ = QFileDialog.getSaveFileName(self, "Guardar como", base, PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            tab.save(path)
            tab.save_as_only = False
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self.status_msg.setText(f"Guardado: {path}")
        return True

    def save_current(self):
        tab = self.current_tab()
        if tab:
            self._save_tab(tab)

    def save_as_current(self):
        tab = self.current_tab()
        if tab:
            self._save_tab_as(tab)

    def save_sanitized_current(self):
        tab = self.current_tab()
        if not tab:
            return
        from .security import sanitize_metadata, sanitize_document
        base = os.path.splitext(os.path.basename(tab.path) if tab.path else "documento")[0]
        suggested = f"{base}_anonimo.pdf"
        out_path, _ = QFileDialog.getSaveFileName(self, "Guardar copia anónima y sanitizada", suggested, PDF_FILTER)
        if not out_path:
            return

        copy_doc = fitz.open()
        copy_doc.insert_pdf(tab.doc)
        sanitize_metadata(copy_doc)
        sanitize_document(copy_doc)
        try:
            copy_doc.save(out_path, deflate=True, garbage=4)
            copy_doc.close()
            QMessageBox.information(
                self,
                "Copia anónima guardada",
                f"Se ha guardado exitosamente la copia sanitizada en:\n{out_path}\n\n"
                "• Metadatos de autor, software e historial: Eliminados.\n"
                "• Identificadores XML / XMP de rastreo: Eliminados.\n"
                "• Scripts y acciones automáticas: Removidos.",
            )
            self.status_msg.setText(f"Copia anónima guardada: {out_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la copia anónima:\n{exc}")

    def _on_link_activated(self, uri: str, text: str):
        from .security import SafeLinkDialog
        dlg = SafeLinkDialog(uri, text=text, parent=self)
        dlg.exec()

    def print_document(self):
        tab = self.current_tab()
        if not tab:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(os.path.basename(tab.path) or "Documento")
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Imprimir documento PDF")
        if dlg.exec() != QDialog.Accepted:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        painter = QPainter(printer)
        try:
            from_pg = printer.fromPage() - 1 if printer.fromPage() > 0 else 0
            to_pg = printer.toPage() - 1 if printer.toPage() > 0 else tab.doc.page_count - 1
            from_pg = max(0, min(tab.doc.page_count - 1, from_pg))
            to_pg = max(from_pg, min(tab.doc.page_count - 1, to_pg))

            dpi = printer.resolution()
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)

            first = True
            for pno in range(from_pg, to_pg + 1):
                if not first:
                    printer.newPage()
                first = False
                page = tab.doc[pno]
                pm = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
                target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                scaled = img.scaled(target_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = target_rect.x() + (target_rect.width() - scaled.width()) / 2
                y = target_rect.y() + (target_rect.height() - scaled.height()) / 2
                painter.drawImage(int(x), int(y), scaled)
            self.status_msg.setText("Documento enviado a la impresora.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error de impresión", f"No se pudo completar la impresión:\n{exc}")
        finally:
            painter.end()
            QApplication.restoreOverrideCursor()

    # --------------------------------------------------------------- controles
    def _update_controls(self):
        tab = self.current_tab()
        has = tab is not None
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_fit_w, self.a_fit_p, self.a_rot_l,
                  self.a_rot_r, self.a_prev, self.a_next, self.a_side, self.a_find,
                  self.a_find_next, self.a_find_prev, self.a_close, self.a_save, self.a_save_as,
                  self.a_save_sanitized, self.a_print,
                  *self.page_actions, *self.tool_actions, *self.utility_actions):
            a.setEnabled(has)
        self.a_undo.setEnabled(has and tab.can_undo)
        self.a_redo.setEnabled(has and tab.can_redo)
        for w in (self.page_spin, self.zoom_combo, self.mode_combo):
            w.setEnabled(has)
        if not has:
            self.page_total.setText(" / 0 ")
            self.status_pages.setText("")
            self.setWindowTitle("Editor PDF Portable")
            self.stack.setCurrentIndex(0)
            self.welcome.refresh_recents()
            return
        self.stack.setCurrentIndex(1)
        v = tab.view
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(v.page_count)
        self.page_spin.setValue(v.current_page + 1)
        self.page_spin.blockSignals(False)
        self.page_total.setText(f" / {v.page_count} ")
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentText(f"{round(v.zoom * 100)}%")
        self.zoom_combo.blockSignals(False)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(v.mode))
        self.mode_combo.blockSignals(False)
        self.status_pages.setText(f"Página {v.current_page + 1} de {v.page_count}   |   {round(v.zoom * 100)}%")
        self.setWindowTitle(f"{tab.title} — Editor PDF Portable")

    def _zoom_from_combo(self, *_):
        text = self.zoom_combo.currentText().replace("%", "").strip().replace(",", ".")
        try:
            value = float(text) / 100.0
        except ValueError:
            self._update_controls()
            return
        self._view_do("set_zoom", value, FIT_NONE)

    def _toggle_side(self):
        tab = self.current_tab()
        if tab:
            tab.toggle_sidebar()

    # ---------------------------------------------------------------- herramientas de interacción
    def _set_active_tool(self, tool: str):
        self._current_tool = tool
        tab = self.current_tab()
        if tab:
            tab.view.set_tool(tool)
        action_map = {
            TOOL_PAN: self.a_tool_pan,
            TOOL_SELECT: self.a_tool_select,
            TOOL_TEXT: self.a_tool_text,
            TOOL_REDACT: self.a_tool_redact,
            TOOL_IMAGE: self.a_tool_image,
            TOOL_SIGN: self.a_tool_sign,
            TOOL_LINK: self.a_tool_link,
            TOOL_PEN: self.a_tool_pen,
            TOOL_HIGHLIGHT: self.a_tool_highlight,
            TOOL_UNDERLINE: self.a_tool_underline,
            TOOL_STRIKEOUT: self.a_tool_strikeout,
            TOOL_NOTE: self.a_tool_note,
        }
        act = action_map.get(tool)
        if act and not act.isChecked():
            act.setChecked(True)

    def _activate_sign_tool(self):
        sig_path = get_signature_path()
        if not os.path.isfile(sig_path):
            dlg = SignatureDialog(self)
            if dlg.exec() != QDialog.Accepted:
                self._set_active_tool(TOOL_PAN)
                return
        self._set_active_tool(TOOL_SIGN)
        self.status_msg.setText("🖋️ Herramienta Firma activa: Haz clic sobre la página donde desees estampar tu firma.")

    def configure_signature(self):
        dlg = SignatureDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.status_msg.setText("Firma personal guardada correctamente.")

    def _on_signature_requested(self, tab: DocTab, pno: int, pt: fitz.Point):
        sig_path = get_signature_path()
        if not os.path.isfile(sig_path):
            dlg = SignatureDialog(self)
            if dlg.exec() != QDialog.Accepted:
                self._set_active_tool(TOOL_PAN)
                return

        try:
            with fitz.open(sig_path) as sig_doc:
                p0 = sig_doc[0]
                img_w, img_h = p0.rect.width, p0.rect.height
        except Exception:
            img_w, img_h = 200.0, 80.0

        target_w = 140.0
        target_h = max(30.0, target_w * (img_h / max(1.0, img_w)))
        rect = fitz.Rect(pt.x - target_w * 0.5, pt.y - target_h * 0.5, pt.x + target_w * 0.5, pt.y + target_h * 0.5)

        self._edit(
            tab,
            lambda d: cops.insert_image(d, pno, rect, sig_path),
            f"Firma estampada en página {pno + 1}",
            goto=pno,
        )
        self._set_active_tool(TOOL_PAN)
        self.status_msg.setText(f"Firma estampada con éxito en página {pno + 1}.")

    def _on_text_requested(self, tab: DocTab, pno: int, rect: fitz.Rect):
        # 1. Buscar si se hizo clic o seleccionó un bloque/tarjeta de texto existente
        center_pt = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        block = cops.find_text_block_at(tab.doc[pno], center_pt, selection_rect=rect)
        if block is None:
            block = cops.find_text_block_at(tab.doc[pno], fitz.Point(rect.x0, rect.y0), selection_rect=rect)

        if block is not None:
            # Edición in-place del texto existente (como en Acrobat Pro)
            dlg = TextEditDialog(
                default_text=block["text"],
                fontsize=block["fontsize"],
                fontname=block["fontname"],
                color=block["color"],
                is_editing=True,
                align=block.get("align", 0),
                parent=self,
            )
            if dlg.exec() != QDialog.Accepted:
                return
            new_text, fontname, size, color, autofit, align = dlg.get_values()
            fill_color = block.get("fill_color", (1.0, 1.0, 1.0))
            card_border = block.get("card_border")
            self._edit(
                tab,
                lambda d: cops.replace_text_block(
                    d, pno, block["bbox"], new_text,
                    fontsize=size, fontname=fontname, color=color,
                    fill_color=fill_color, autofit=autofit, align=align,
                    card_border=card_border,
                ),
                f"Texto editado en página {pno + 1}",
                goto=pno,
            )
        else:
            # Inserción de un nuevo texto en área libre
            dlg = TextEditDialog(is_editing=False, parent=self)
            if dlg.exec() != QDialog.Accepted:
                return
            new_text, fontname, size, color, _, align = dlg.get_values()
            self._edit(
                tab,
                lambda d: cops.add_text_box(
                    d, pno, rect, new_text,
                    fontsize=size, fontname=fontname, color=color, align=align,
                ),
                f"Nuevo texto insertado en página {pno + 1}",
                goto=pno,
            )

    def _on_redact_requested(self, tab: DocTab, pno: int, rect: fitz.Rect):
        r = QMessageBox.warning(
            self,
            "Confirmar censura",
            f"¿Aplicar censura permanente en el área seleccionada de la página {pno + 1}?\n\n"
            "El texto y las imágenes debajo serán eliminados de forma irreversible.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if r != QMessageBox.Yes:
            return
        self._edit(
            tab,
            lambda d: cops.apply_redaction(d, pno, rect),
            f"Censura permanente aplicada en página {pno + 1}",
            goto=pno,
        )

    def _on_image_requested(self, tab: DocTab, pno: int, rect: fitz.Rect):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen a insertar",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;Todos los archivos (*)",
        )
        if not path:
            return
        self._edit(
            tab,
            lambda d: cops.insert_image(d, pno, rect, path),
            f"Imagen insertada en página {pno + 1}",
            goto=pno,
        )

    def _on_link_requested(self, tab: DocTab, pno: int, rect: fitz.Rect):
        dlg = AddLinkDialog(tab.doc.page_count, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        uri = dlg.uri() if dlg.is_url() else ""
        target_page = dlg.target_page() if not dlg.is_url() else None
        self._edit(
            tab,
            lambda d: cops.add_hyperlink(d, pno, rect, uri=uri, target_page=target_page),
            f"Enlace añadido en página {pno + 1}",
            goto=pno,
        )

    def _on_pen_stroke(self, tab: DocTab, pno: int, stroke: list[tuple[float, float]]):
        if not stroke or len(stroke) < 2:
            return
        self._edit(
            tab,
            lambda d: annot_mod.add_ink_annotation(d, pno, [stroke], color=(0.0, 0.2, 0.8), width=2.5),
            f"Trazo de lápiz añadido en página {pno + 1}",
            goto=pno,
        )

    def _on_note_requested(self, tab: DocTab, pno: int, pt: fitz.Point):
        dlg = AddNoteDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        txt = dlg.content()
        auth = dlg.author()
        self._edit(
            tab,
            lambda d: annot_mod.add_note_annotation(d, pno, pt, txt, author=auth),
            f"Nota adhesiva añadida en página {pno + 1}",
            goto=pno,
        )

    def _on_highlight_requested(self, tab: DocTab, pno: int, rect: fitz.Rect | list):
        rects = rect if isinstance(rect, list) else [rect]
        self._edit(
            tab,
            lambda d: annot_mod.add_highlight_annotation(d, pno, rects),
            f"Texto resaltado en página {pno + 1}",
            goto=pno,
        )

    def _on_underline_requested(self, tab: DocTab, pno: int, rect: fitz.Rect | list):
        rects = rect if isinstance(rect, list) else [rect]
        self._edit(
            tab,
            lambda d: annot_mod.add_underline_annotation(d, pno, rects),
            f"Subrayado añadido en página {pno + 1}",
            goto=pno,
        )

    def _on_strikeout_requested(self, tab: DocTab, pno: int, rect: fitz.Rect | list):
        rects = rect if isinstance(rect, list) else [rect]
        self._edit(
            tab,
            lambda d: annot_mod.add_strikeout_annotation(d, pno, rects),
            f"Tachado añadido en página {pno + 1}",
            goto=pno,
        )

    def fill_form_fields(self):
        tab = self.current_tab()
        if not tab:
            return
        fields = forms_mod.get_form_fields(tab.doc)
        if not fields:
            QMessageBox.information(self, "Formularios", "Este documento no contiene campos interactivos de formulario (AcroForms).")
            return
        dlg = FillFormsDialog(fields, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        self._edit(
            tab,
            lambda d: forms_mod.update_form_fields(d, vals),
            f"Se actualizaron {len(vals)} campos de formulario",
        )

    def flatten_form_fields(self):
        tab = self.current_tab()
        if not tab:
            return
        fields = forms_mod.get_form_fields(tab.doc)
        if not fields:
            QMessageBox.information(self, "Formularios", "Este documento no contiene campos de formulario para aplanar.")
            return
        r = QMessageBox.question(
            self,
            "Aplanar formulario",
            "¿Deseas aplanar los campos de formulario?\n\n"
            "Esta acción convertirá los campos en contenido estático fijo e impedirá su modificación posterior.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if r == QMessageBox.Yes:
            self._edit(
                tab,
                lambda d: forms_mod.flatten_forms(d),
                "Campos de formulario aplanados con éxito",
            )

    def find_and_redact(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = FindRedactDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        phrase = dlg.phrase()
        color = dlg.fill_color()
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        matches_count = [0]
        def _do_find_redact(doc):
            matches_count[0] = cops.redact_search_phrase(doc, phrase, pages=pages, fill_color=color)

        self._edit(
            tab,
            _do_find_redact,
            f"Se censuraron {matches_count[0]} apariciones de «{phrase}»",
            goto=tab.view.current_page,
        )
        QMessageBox.information(
            self,
            "Censura completada",
            f"Se censuraron {matches_count[0]} apariciones de «{phrase}» de forma permanente.",
        )

    def extract_all_images(self):
        tab = self.current_tab()
        if not tab:
            return
        initial_dir = os.path.dirname(tab.path) if tab.path else ""
        out_dir = QFileDialog.getExistingDirectory(self, "Carpeta donde guardar las imágenes", initial_dir)
        if not out_dir:
            return
        try:
            extracted = cops.extract_images(tab.doc, out_dir)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Error al extraer imágenes", str(exc))
            return
        if not extracted:
            QMessageBox.information(self, "Imágenes", "No se encontraron imágenes incrustadas en el documento.")
        else:
            QMessageBox.information(
                self,
                "Extracción completada",
                f"Se extrajeron {len(extracted)} imágenes en:\n{out_dir}",
            )

    # ---------------------------------------------------------------- exportar / convertir (Fase 6)
    def export_to_word(self):
        tab = self.current_tab()
        if not tab:
            return
        base = os.path.splitext(tab.path)[0] + ".docx" if tab.path else "documento.docx"
        out_path, _ = QFileDialog.getSaveFileName(self, "Exportar a Microsoft Word", base, "Documento Word (*.docx)")
        if not out_path:
            return
        try:
            run_blocking(
                self,
                "Convirtiendo PDF a Microsoft Word (.docx)…\nEsto puede tardar unos segundos.",
                lambda: conv.convert_to_word(tab.doc, out_path, src_path=tab.path),
            )
            QMessageBox.information(self, "Conversión completada", f"Se exportó exitosamente a:\n{out_path}")
            self.status_msg.setText(f"Exportado a Word: {out_path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error de conversión", str(exc))

    def export_to_excel(self):
        tab = self.current_tab()
        if not tab:
            return
        base = os.path.splitext(tab.path)[0] + ".xlsx" if tab.path else "tablas.xlsx"
        out_path, _ = QFileDialog.getSaveFileName(self, "Exportar tablas a Excel", base, "Libro de Excel (*.xlsx)")
        if not out_path:
            return
        try:
            total_tables = run_blocking(
                self,
                "Extrayendo tablas a Excel…",
                lambda: conv.convert_to_excel(tab.doc, out_path),
            )
            msg = f"Se extrajeron {total_tables} tablas a:\n{out_path}" if total_tables else f"Se exportó el contenido a:\n{out_path}"
            QMessageBox.information(self, "Exportación a Excel", msg)
            self.status_msg.setText(f"Exportado a Excel: {out_path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error de exportación", str(exc))

    def export_to_images(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = ConvertImagesDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        out_dir = dlg.folder()
        fmt = dlg.format()
        dpi = dlg.dpi()
        try:
            exported = run_blocking(
                self,
                "Exportando páginas como imágenes…",
                lambda: conv.convert_to_images(tab.doc, out_dir, fmt=fmt, dpi=dpi, pages=pages),
            )
            QMessageBox.information(self, "Exportación completada", f"Se exportaron {len(exported)} páginas en:\n{out_dir}")
            self.status_msg.setText(f"Exportadas {len(exported)} imágenes a {out_dir}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al exportar imágenes", str(exc))

    def export_to_text(self):
        tab = self.current_tab()
        if not tab:
            return
        base = os.path.splitext(tab.path)[0] + ".txt" if tab.path else "documento.txt"
        out_path, _ = QFileDialog.getSaveFileName(self, "Exportar a texto plano", base, "Archivo de texto (*.txt)")
        if not out_path:
            return
        try:
            conv.convert_to_text(tab.doc, out_path)
            QMessageBox.information(self, "Exportación completada", f"Texto exportado en:\n{out_path}")
            self.status_msg.setText(f"Exportado a texto: {out_path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(exc))

    def export_to_html(self):
        tab = self.current_tab()
        if not tab:
            return
        base = os.path.splitext(tab.path)[0] + ".html" if tab.path else "documento.html"
        out_path, _ = QFileDialog.getSaveFileName(self, "Exportar a HTML", base, "Página Web (*.html)")
        if not out_path:
            return
        try:
            conv.convert_to_html(tab.doc, out_path)
            QMessageBox.information(self, "Exportación completada", f"Página HTML exportada en:\n{out_path}")
            self.status_msg.setText(f"Exportado a HTML: {out_path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(exc))

    # ---------------------------------------------------------------- OCR y Optimización (Fases 5 y 10)
    def run_ocr(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = OcrDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        lang = dlg.language()
        dpi = dlg.dpi()
        try:
            ocr_doc = run_blocking(
                self,
                f"Ejecutando reconocimiento de texto (OCR) en {len(pages)} páginas…\nEsto puede tardar unos instantes.",
                lambda: ocr.ocr_document(tab.doc, language=lang, dpi=dpi, pages=pages),
            )
            name = (os.path.splitext(os.path.basename(tab.path))[0] if tab.path else "documento") + "_OCR.pdf"
            self._add_tab("", ocr_doc, save_as_only=True, modified=True, suggested=name)
            self.status_msg.setText(f"OCR finalizado: documento con texto buscable abierto como '{name}'")
            QMessageBox.information(self, "OCR Completado", "El documento con texto reconocido y buscable se ha abierto en una nueva pestaña.\nGuardalo con Ctrl+S.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error en OCR", str(exc))

    def optimize_document(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = OptimizeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        base = (os.path.splitext(tab.path)[0] if tab.path else "documento") + "_optimizado.pdf"
        out_path, _ = QFileDialog.getSaveFileName(self, "Guardar PDF optimizado", base, PDF_FILTER)
        if not out_path:
            return
        compress = dlg.compress_images()
        quality = dlg.image_quality()
        sanitize = dlg.sanitize()
        try:
            orig_sz, final_sz, saving = run_blocking(
                self,
                "Optimizando y comprimiendo el documento…",
                lambda: opt.optimize_document(
                    tab.doc, out_path, compress_images=compress, image_quality=quality, sanitize_metadata=sanitize
                ),
            )
            orig_mb = round(orig_sz / 1024 / 1024, 2)
            final_mb = round(final_sz / 1024 / 1024, 2)
            msg = (
                f"¡Optimización finalizada!\n\n"
                f"• Tamaño original: {orig_mb} MB ({orig_sz:,} bytes)\n"
                f"• Tamaño optimizado: {final_mb} MB ({final_sz:,} bytes)\n"
                f"• Reducción de peso: {saving}%\n\n"
                f"Guardado en: {out_path}"
            )
            QMessageBox.information(self, "Optimización completada", msg)
            self.status_msg.setText(f"Optimizado: ahorro del {saving}% ({final_mb} MB)")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al optimizar", str(exc))

    # ---------------------------------------------------------------- crear PDF
    def create_from_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Crear PDF desde archivos", "", creation.file_filter())
        if paths:
            self._create_from_dialog(paths)

    def _create_from_dialog(self, files: list[str]):
        dlg = CombineDialog(files, self)
        if dlg.exec() != QDialog.Accepted:
            return
        paths = dlg.files()
        office = [p for p in paths if creation.classify(p) == "office"]
        tmp = tempfile.mkdtemp(prefix="editorpdf_")
        try:
            converted: dict[str, str] = {}
            if office:
                converted = run_blocking(
                    self, "Convirtiendo documentos de Office con LibreOffice…\n(la primera vez puede tardar)",
                    lambda: creation.convert_office_files(office, tmp))
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                doc = creation.build_pdf(paths, dlg.mode(), dlg.bookmarks.isChecked(), converted)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo crear el PDF", str(exc))
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        name = os.path.splitext(os.path.basename(paths[0]))[0] if len(paths) == 1 else "combinado"
        self._add_tab("", doc, save_as_only=True, modified=True, suggested=f"{name}.pdf")
        self.status_msg.setText(f"PDF creado con {doc.page_count} páginas. Guardalo con Ctrl+S.")

    def create_from_clipboard(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(self, "Portapapeles", "No hay ninguna imagen en el portapapeles.")
            return
        tmp = tempfile.mkdtemp(prefix="editorpdf_")
        try:
            path = os.path.join(tmp, "portapapeles.png")
            image.save(path, "PNG")
            doc = creation.images_to_pdf([path], "image")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo crear el PDF", str(exc))
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._add_tab("", doc, save_as_only=True, modified=True, suggested="portapapeles.pdf")

    def create_from_scanner(self):
        tmp = tempfile.mkdtemp(prefix="editorpdf_scan_")
        try:
            images: list[str] = []
            while True:
                try:
                    path = run_blocking(self, "Esperando al escáner…",
                                        lambda n=len(images) + 1: creation.scan_one_page(tmp, n))
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "Escáner", str(exc))
                    break
                if not path:
                    break
                images.append(path)
                if QMessageBox.question(
                        self, "Escáner", f"Página {len(images)} escaneada.\n¿Escanear otra página?") != QMessageBox.Yes:
                    break
            if images:
                try:
                    doc = creation.images_to_pdf(images, "a4")
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "No se pudo crear el PDF", str(exc))
                    return
                self._add_tab("", doc, save_as_only=True, modified=True, suggested="escaneo.pdf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def create_blank(self):
        self._add_tab("", creation.blank_document(1), save_as_only=True, modified=True, suggested="documento.pdf")

    # --------------------------------------------------- operaciones de páginas
    def _edit(self, tab: DocTab, fn, message: str, select=None, goto=None) -> bool:
        try:
            tab.run_edit(fn, select=select, goto=goto)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo completar", str(exc))
            return False
        self.status_msg.setText(message)
        return True

    @staticmethod
    def _label(pages: list[int]) -> str:
        return f"{len(pages)} página" + ("s" if len(pages) != 1 else "")

    def insert_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insertar páginas desde…", "", f"{PDF_FILTER};;Todos los archivos (*)")
        if not path:
            return
        sel = tab.selected_pages()
        options = {
            "Después de la selección": sel[-1] + 1,
            "Antes de la selección": sel[0],
            "Al inicio del documento": 0,
            "Al final del documento": tab.doc.page_count,
        }
        choice, ok = QInputDialog.getItem(self, "Insertar páginas", "Posición:", list(options), 0, False)
        if not ok:
            return
        at = options[choice]
        self._edit(tab, lambda d: ops.insert_from_file(d, path, at),
                   f"Páginas insertadas desde {os.path.basename(path)}", goto=at)

    def insert_blank(self):
        tab = self.current_tab()
        if not tab:
            return
        sel = tab.selected_pages()
        at = sel[-1] + 1
        self._edit(tab, lambda d: ops.insert_blank(d, at, like=sel[-1]),
                   "Página en blanco insertada", select=[at])

    def replace_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        sel = tab.selected_pages()
        path, _ = QFileDialog.getOpenFileName(self, "Reemplazar con páginas de…", "", PDF_FILTER)
        if not path:
            return
        first, ok = QInputDialog.getInt(
            self, "Reemplazar páginas",
            f"Se reemplazan {self._label(sel)}.\nPrimera página del archivo de origen a usar:", 1, 1, 100000)
        if not ok:
            return
        self._edit(tab, lambda d: ops.replace_pages(d, sel, path, first - 1),
                   f"Reemplazadas {self._label(sel)}", select=sel)

    def extract_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        sel = tab.selected_pages()
        base = os.path.splitext(tab.path)[0] + "_extraido.pdf" if tab.path else "extraido.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar páginas extraídas", base, PDF_FILTER)
        if not path:
            return
        try:
            ops.extract_pages(tab.doc, sel, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo extraer", str(exc))
            return
        self.status_msg.setText(f"Extraídas {self._label(sel)} a {path}")

    def delete_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        sel = tab.selected_pages()
        if len(sel) >= tab.doc.page_count:
            QMessageBox.warning(self, "Eliminar", "No se pueden eliminar todas las páginas del documento.")
            return
        if QMessageBox.question(self, "Eliminar páginas", f"¿Eliminar {self._label(sel)}?") != QMessageBox.Yes:
            return
        goto = min(sel[0], tab.doc.page_count - len(sel) - 1)
        self._edit(tab, lambda d: ops.delete_pages(d, sel), f"Eliminadas {self._label(sel)}", select=[goto])

    def duplicate_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        sel = sorted(set(tab.selected_pages()))
        new_sel = [p + k + 1 for k, p in enumerate(sel)]
        self._edit(tab, lambda d: ops.duplicate_pages(d, sel), f"Duplicadas {self._label(sel)}", select=new_sel)

    def rotate_pages(self, angle: int):
        tab = self.current_tab()
        if not tab:
            return
        sel = tab.selected_pages()
        self._edit(tab, lambda d: ops.rotate_pages(d, sel, angle), f"Giradas {self._label(sel)}", select=sel)

    def move_pages(self, direction: int):
        tab = self.current_tab()
        if not tab:
            return
        sel = sorted(set(tab.selected_pages()))
        order = ops.move_order(tab.doc.page_count, sel, direction)
        if order is None:
            return
        new_sel = [order.index(p) for p in sel]
        self._edit(tab, lambda d: ops.reorder(d, order), "Páginas movidas", select=new_sel)

    def split_document(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = SplitDialog(tab.doc.page_count, bool(tab.doc.get_toc()), self)
        if tab.path:
            dlg.folder.setText(os.path.dirname(tab.path))
        if dlg.exec() != QDialog.Accepted:
            return
        out_dir = dlg.folder.text().strip()
        base = os.path.splitext(os.path.basename(tab.path))[0] if tab.path else "documento"
        mode = dlg.mode.currentIndex()
        try:
            os.makedirs(out_dir, exist_ok=True)
            if mode == 0:
                files = ops.split_every(tab.doc, dlg.count.value(), out_dir, base)
            elif mode == 1:
                files = ops.split_ranges(tab.doc, dlg.ranges.text(), out_dir, base)
            else:
                files = ops.split_by_bookmarks(tab.doc, out_dir, base)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo dividir", str(exc))
            return
        self.status_msg.setText(f"Documento dividido en {len(files)} archivos en {out_dir}")
        QMessageBox.information(self, "Dividir documento", f"Se crearon {len(files)} archivos en:\n{out_dir}")

    def _scoped_pages(self, tab: DocTab, dlg) -> list[int] | None:
        try:
            return dlg.scope.pages(tab.doc.page_count, tab.selected_pages())
        except ValueError as exc:
            QMessageBox.warning(self, "Rango no válido", str(exc))
            return None

    def crop_pages(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = CropDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        m = dlg.margins_pt()
        self._edit(tab, lambda d: ops.crop_pages(d, pages, m["left"], m["top"], m["right"], m["bottom"]),
                   f"Recortadas {self._label(pages)}", goto=tab.view.current_page)

    def watermark(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = WatermarkDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        self._edit(
            tab,
            lambda d: ops.add_watermark(
                d, pages, dlg.text.text(), dlg.size.value(), dlg.color.rgb(),
                dlg.opacity.value() / 100, dlg.angle.value(), dlg.behind.isChecked()),
            f"Marca de agua aplicada a {self._label(pages)}", goto=tab.view.current_page)

    def background(self):
        tab = self.current_tab()
        if not tab:
            return
        color = QColorDialog.getColor(QColor(255, 255, 224), self, "Color de fondo")
        if not color.isValid():
            return
        rgb = (color.redF(), color.greenF(), color.blueF())
        pages = list(range(tab.doc.page_count))
        self._edit(tab, lambda d: ops.add_background(d, pages, rgb),
                   "Color de fondo aplicado a todas las páginas", goto=tab.view.current_page)

    def header_footer(self):
        tab = self.current_tab()
        if not tab:
            return
        dlg = HeaderFooterDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pages = self._scoped_pages(tab, dlg)
        if pages is None:
            return
        self._edit(
            tab,
            lambda d: ops.add_header_footer(
                d, pages, dlg.text.text(), dlg.position.currentText(), dlg.size.value(),
                dlg.start.value(), dlg.digits.value(), dlg.color.rgb()),
            f"Texto añadido a {self._label(pages)}", goto=tab.view.current_page)

    # ---------------------------------------------------------------- búsqueda
    def show_find_bar(self):
        tab = self.current_tab()
        if tab:
            tab.show_search()

    def _find_next(self):
        tab = self.current_tab()
        if tab:
            tab._find_next()

    def _find_prev(self):
        tab = self.current_tab()
        if tab:
            tab._find_prev()

    # ---------------------------------------------------------------- documentos recientes
    def _update_recent_menu(self):
        if not hasattr(self, "menu_recents"):
            return
        self.menu_recents.clear()
        recents = get_recent_files()
        if not recents:
            act = self.menu_recents.addAction("Sin documentos recientes")
            act.setEnabled(False)
            return

        for p in recents:
            name = os.path.basename(p)
            act = self.menu_recents.addAction(f"📄 {name}")
            act.setToolTip(p)
            act.triggered.connect(lambda _checked=False, target=p: self.open_file(target))

        self.menu_recents.addSeparator()
        act_clear = self.menu_recents.addAction("Limpiar historial de recientes")
        act_clear.triggered.connect(self._clear_recents)

    def _clear_recents(self):
        clear_recent_files()
        self._update_recent_menu()
        self.welcome.refresh_recents()

    # --------------------------------------------------------- arrastrar y soltar
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        others: list[str] = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_file(path)
            elif creation.classify(path):
                others.append(path)
        if others:
            self._create_from_dialog(others)

    def closeEvent(self, event):
        while self.tabs.count():
            if not self.close_tab(0):
                event.ignore()
                return
        event.accept()
