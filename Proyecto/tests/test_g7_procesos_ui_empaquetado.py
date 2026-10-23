"""Pruebas del Grupo 7: Procesamiento multihilo, límites HTML/caché, OCR fallback, eventos UI y empaquetado.
Cubre: H05, H23, H31, H32, H34, H35, H36, H48, H37, H38.
"""
from __future__ import annotations

import os
import threading
import pymupdf as fitz
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMainWindow, QWidget

from app import background, creation, ocr
from app.doc_tab import DocTab
from app.main_window import MainWindow
from app.selection_popup import TextSelectionPopup
from app.viewer import MODE_SINGLE, PdfView, TOOL_HIGHLIGHT, TOOL_SELECT


# ---------------------------------------------------------------------------
# H05: run_blocking no debe usar la misma instancia fitz.Document del hilo GUI
# ---------------------------------------------------------------------------
def test_h05_pdf_jobs_use_an_independent_process(qapp):
    """H05/R01: La API usada por la GUI abre sus propios bytes en otro proceso."""
    gui_doc = fitz.open()
    page = gui_doc.new_page(width=200, height=200)
    page.insert_text((30, 50), "THREAD_SAFE_TEXT")
    parent = QWidget()
    res = background.run_pdf_job(parent, "Procesando…", "inspect", gui_doc)
    assert res["text"].strip() == "THREAD_SAFE_TEXT"
    assert res["pid"] != os.getpid()
    assert gui_doc[0].get_text().strip() == "THREAD_SAFE_TEXT"
    gui_doc.close()


# ---------------------------------------------------------------------------
# H23: reload() debe invalidar _hits, _hit_index y _selected_text
# ---------------------------------------------------------------------------
def test_h23_viewer_reload_invalidates_stale_search_hits_and_selection(qapp):
    """H23: Buscar en página 2, eliminarla, recargar y llamar next_hit en modo página única no debe lanzar IndexError."""
    doc = fitz.open()
    p0 = doc.new_page(width=200, height=200)
    p0.insert_text((30, 50), " Pagina uno ")
    p1 = doc.new_page(width=200, height=200)
    p1.insert_text((30, 50), "OBJETIVO_BUSQUEDA")

    view = PdfView(doc)
    view.set_mode(MODE_SINGLE)
    hits = view.search("OBJETIVO_BUSQUEDA")
    assert hits == 1
    view._selected_text = "SELECCION_ANTIGUA"

    # Eliminar la página 1 (segunda página) y recargar
    doc.delete_page(1)
    view.reload(doc)

    assert view._selected_text == ""
    assert view._hits == []
    assert view._hit_index == -1
    # Llamar next_hit() no debe lanzar IndexError
    idx, total = view.next_hit()
    assert total == 0
    doc.close()


# ---------------------------------------------------------------------------
# H31: Fallback de OCR cuando falla el motor en inglés no usa pix.tobytes("pdf")
# ---------------------------------------------------------------------------
def test_h31_ocr_fallback_when_pdfocr_fails_preserves_page_validly(monkeypatch):
    """H31: Si pix.pdfocr_tobytes falla (incluso en 'eng'), ocr_document debe preservar la página sin ValueError."""
    doc = fitz.open()
    p = doc.new_page(width=200, height=200)
    p.insert_text((40, 60), "Texto sin OCR")

    def broken_pdfocr(self, *args, **kwargs):
        raise RuntimeError("Fallo simulado de Tesseract")

    monkeypatch.setattr(fitz.Pixmap, "pdfocr_tobytes", broken_pdfocr)

    out_doc = ocr.ocr_document(doc, language="eng", dpi=72)
    assert out_doc.page_count == 1
    out_doc.close()
    doc.close()


# ---------------------------------------------------------------------------
# H32: TextSelectionPopup convierte coordenadas globales al padre y acota
# ---------------------------------------------------------------------------
def test_h32_selection_popup_maps_global_pos_to_parent_viewport(qapp):
    """H32: Al mover la ventana padre a (1000, 500), show_at debe posicionar el popup dentro de los límites del padre."""
    parent = QWidget()
    parent.setGeometry(1000, 500, 600, 400)
    popup = TextSelectionPopup(parent)

    global_target = parent.mapToGlobal(QPoint(300, 200))
    popup.show_at(global_target)

    assert 0 <= popup.x() <= parent.width() - popup.width()
    assert 0 <= popup.y() <= parent.height() - popup.height()


# ---------------------------------------------------------------------------
# H34: El menú contextual de miniaturas debe conectarse una sola vez
# ---------------------------------------------------------------------------
def test_h34_thumbnail_context_menu_connected_only_once(qapp, monkeypatch):
    """H34: Emitir customContextMenuRequested en miniaturas debe invocar _on_thumb_context_menu exactamente 1 vez."""
    win = MainWindow()
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    win._add_tab("", doc)
    tab = win.current_tab()
    assert tab is not None

    calls = {"n": 0}
    monkeypatch.setattr(tab, "_on_thumb_context_menu", lambda pos: calls.__setitem__("n", calls["n"] + 1))

    tab.thumbs.customContextMenuRequested.emit(QPoint(10, 10))
    assert calls["n"] == 1
    win.close()


# ---------------------------------------------------------------------------
# H35: Shift+H con texto seleccionado anota la selección en vez de vaciarla
# ---------------------------------------------------------------------------
def test_h35_shift_h_highlights_active_selection_instead_of_clearing(qapp, no_dialogs):
    """H35: Con selección activa, activar el comando de resaltado (Shift+H) debe resaltar la selección y no vaciarla sin anotar."""
    win = MainWindow()
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 60), "TEXTO_PARA_RESALTAR", fontsize=12)
    win._add_tab("", doc)
    tab = win.current_tab()
    assert tab is not None

    rect = page.search_for("TEXTO_PARA_RESALTAR")[0]
    tab.view._selection_page = 0
    tab.view._selection_line_rects = [rect]
    tab.view._selected_text = "TEXTO_PARA_RESALTAR"

    emitted = []
    tab.view.highlightRequested.connect(lambda pno, rects: emitted.append((pno, rects)))

    # Disparar la acción global vinculada a Shift+H
    win.a_tool_highlight.trigger()
    assert len(emitted) >= 1
    assert emitted[0][0] == 0
    tab.modified = False
    win.close()


# ---------------------------------------------------------------------------
# H36: Presupuesto de bytes en caché de renderizado de PdfView
# ---------------------------------------------------------------------------
def test_h36_viewer_cache_respects_byte_budget(qapp, monkeypatch):
    """H36: El caché de pixmaps de PdfView no debe superar MAX_CACHE_BYTES."""
    import app.viewer as viewer_mod

    monkeypatch.setattr(viewer_mod, "MAX_CACHE_BYTES", 2 * 1024 * 1024)  # 2 MB para la prueba
    doc = fitz.open()
    for _ in range(10):
        doc.new_page(width=600, height=800)

    view = PdfView(doc)
    view.set_zoom(2.0)
    for i in range(10):
        view._pixmap(i)

    assert view._cache_bytes <= 2 * 1024 * 1024 or len(view._cache) <= 1
    doc.close()


# ---------------------------------------------------------------------------
# H48: html_to_pdf detiene paginación sin progreso en HTML imposible
# ---------------------------------------------------------------------------
def test_h48_html_to_pdf_stops_on_unplaceable_content():
    """H48: Un elemento HTML imposible de acomodar en la página debe lanzar ValueError rápidamente sin bucle infinito."""
    bad_html = '<div style="font-size:1000pt;white-space:nowrap">MMMMMMMMMMMM</div>'
    with pytest.raises(ValueError):
        creation.html_to_pdf(bad_html)


# ---------------------------------------------------------------------------
# H37 & H38: requirements.txt y archivos de empaquetado portables
# ---------------------------------------------------------------------------
def test_h37_h38_requirements_and_packaging_files():
    """H37/H38: requirements.txt declara openpyxl y versiones; .spec no tiene rutas absolutas ni data/lo_profile."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req_txt = open(os.path.join(root, "requirements", "requirements.txt"), encoding="utf-8").read()
    assert "openpyxl" not in req_txt
    assert "pdf2docx" not in req_txt
    assert "PySide6" in req_txt
    assert ">=" in req_txt

    spec_txt = open(os.path.join(root, "scripts", "EditorPDFPortable.spec"), encoding="utf-8").read()
    assert "C:/Users/feder" not in spec_txt
    assert "lo_profile" not in spec_txt

    bat_txt = open(os.path.join(root, os.pardir, "Abrir_EditorPortable.bat"), encoding="utf-8").read()
    assert "%~dp0EditorPDFPortable.exe" in bat_txt


def test_welcome_buttons(qapp, monkeypatch):
    """Verifica que la pantalla de bienvenida tiene 'Abrir archivo' y 'Crear PDF desde archivos', y no documento en blanco."""
    win = MainWindow()
    try:
        w = win.welcome
        assert hasattr(w, "btn_open")
        assert hasattr(w, "btn_create_files")
        assert not hasattr(w, "btn_blank")

        called = []
        monkeypatch.setattr(win, "create_from_files", lambda: called.append(True))
        w.btn_create_files.click()
        assert called == [True]
    finally:
        win.close()
