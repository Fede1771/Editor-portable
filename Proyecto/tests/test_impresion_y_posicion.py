"""Regresiones de Ctrl+P, salida de impresión y posición después de editar."""
from __future__ import annotations

import pymupdf as fitz
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPageRanges
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app.doc_tab import DocTab
from app.main_window import MainWindow
from app.printing import print_page_indices, print_pdf
from app.viewer import MODE_CONTINUOUS, MODE_SINGLE, MODE_TWO


def make_doc():
    doc = fitz.open()
    for i in range(8):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 600), f"Pagina {i + 1}")
    return doc


@pytest.mark.parametrize("mode", [MODE_CONTINUOUS, MODE_SINGLE, MODE_TWO])
def test_edit_undo_redo_keep_scroll_position(qapp, mode):
    tab = DocTab("", make_doc())
    try:
        tab.resize(1100, 700)
        tab.show()
        qapp.processEvents()
        view = tab.view
        view.set_mode(mode)
        view.set_zoom(2)
        view.goto_page(4)
        view.verticalScrollBar().setValue(view.verticalScrollBar().value() + 350)
        view.horizontalScrollBar().setValue(120)
        qapp.processEvents()
        position = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
        current = view.current_page
        tab.run_edit(lambda d: d[4].insert_text((50, 650), "Texto editado"), goto=4)
        for operation in (None, tab.undo, tab.redo):
            if operation:
                operation()
            qapp.processEvents()
            assert (view.horizontalScrollBar().value(), view.verticalScrollBar().value()) == position
            assert view.current_page == current
            assert tab.thumbs.currentRow() == current
        assert "Texto editado" in tab.doc[4].get_text()
    finally:
        tab.close_document()
        tab.close()


def test_failed_edit_keeps_position_and_restores_document(qapp):
    tab = DocTab("", make_doc())
    try:
        tab.resize(1100, 700)
        tab.show()
        qapp.processEvents()
        tab.view.goto_page(5)
        tab.view.verticalScrollBar().setValue(tab.view.verticalScrollBar().value() + 200)
        position = tab.view.verticalScrollBar().value()

        def fail(doc):
            doc[5].insert_text((50, 650), "Cambio fallido")
            raise ValueError("fallo simulado")

        with pytest.raises(ValueError, match="simulado"):
            tab.run_edit(fail)
        qapp.processEvents()
        assert tab.view.verticalScrollBar().value() == position
        assert "Cambio fallido" not in tab.doc[5].get_text()
    finally:
        tab.close_document()
        tab.close()


def test_explicit_destination_still_navigates(qapp):
    tab = DocTab("", make_doc())
    try:
        tab.run_edit(lambda d: d.new_page(), select=[8], goto=8)
        assert tab.view.current_page == 8
        assert tab.view.is_page_visible(8)
    finally:
        tab.close_document()
        tab.close()


def test_ctrl_p_works_with_document_focus(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(MainWindow, "print_document", lambda self: calls.append(self.current_tab()))
    win = MainWindow()
    try:
        assert not win.a_print.isEnabled()
        win._add_tab("", make_doc())
        win.show()
        win.activateWindow()
        win.current_tab().view.setFocus()
        qapp.processEvents()
        QTest.keyClick(win.current_tab().view, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
        qapp.processEvents()
        assert calls == [win.current_tab()]
    finally:
        win.close()


def test_native_dialog_uses_installed_printer_and_document_limits(qapp, monkeypatch):
    monkeypatch.setattr(QPrinterInfo, "availablePrinters", lambda: [QPrinterInfo()])
    observed = []

    def cancel(dialog):
        observed.append(dialog)
        assert dialog.minPage() == 1
        assert dialog.maxPage() == 8
        assert dialog.testOption(QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage)
        assert dialog.testOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange)
        assert dialog.printer().outputFormat() == QPrinter.OutputFormat.NativeFormat
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QPrintDialog, "exec", cancel)
    win = MainWindow()
    try:
        win._add_tab("", make_doc())
        win.print_document()
        assert len(observed) == 1
        assert QApplication.overrideCursor() is None
    finally:
        win.close()


def test_no_installed_printers_explains_how_to_add_one(qapp, monkeypatch, no_dialogs):
    monkeypatch.setattr(QPrinterInfo, "availablePrinters", lambda: [])
    win = MainWindow()
    try:
        win._add_tab("", make_doc())
        win.print_document()
        assert any("Sin impresoras instaladas" in text for _, text in no_dialogs[0])
    finally:
        win.close()


@pytest.mark.parametrize("mode,expected", [
    (QPrinter.PrintRange.AllPages, list(range(8))),
    (QPrinter.PrintRange.CurrentPage, [4]),
    (QPrinter.PrintRange.Selection, [1, 5]),
    (QPrinter.PrintRange.PageRange, [1, 2, 3]),
])
def test_print_range_and_reverse_order(qapp, mode, expected):
    doc = make_doc()
    try:
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPrintRange(mode)
        printer.setFromTo(2, 4)
        assert print_page_indices(doc, printer, 4, [5, 1]) == expected
        printer.setPageOrder(QPrinter.PageOrder.LastPageFirst)
        assert print_page_indices(doc, printer, 4, [5, 1]) == expected[::-1]
    finally:
        doc.close()


def test_print_disjoint_ranges(qapp):
    doc = make_doc()
    try:
        printer = QPrinter()
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setPageRanges(QPageRanges.fromString("2-3,6"))
        assert print_page_indices(doc, printer, 0, []) == [1, 2, 5]
    finally:
        doc.close()


def test_print_renders_unsaved_changes_and_annotations(qapp, tmp_path):
    doc = make_doc()
    try:
        # Una modificación sin guardar debe llegar al trabajo de impresión.
        doc[4].draw_rect(doc[4].rect, color=None, fill=(1, 0, 0))
        annot = doc[4].add_rect_annot(fitz.Rect(200, 300, 400, 500))
        annot.set_colors(fill=(0, 0, 1))
        annot.update()
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        output = tmp_path / "impresion.pdf"
        printer.setOutputFileName(str(output))
        printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
        print_pdf(doc, printer, 4, [])
        with fitz.open(output) as result:
            assert result.page_count == 1
            pix = result[0].get_pixmap()
            assert pix.pixel(pix.width // 2, pix.height // 2) == pytest.approx((0, 0, 255), abs=2)
            assert pix.pixel(pix.width // 4, pix.height // 4) == pytest.approx((255, 0, 0), abs=2)
    finally:
        doc.close()


def test_print_failure_does_not_report_success(qapp, tmp_path):
    doc = make_doc()
    try:
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(tmp_path / "no_existe" / "impresion.pdf"))
        with pytest.raises(RuntimeError, match="iniciar"):
            print_pdf(doc, printer, 0, [])
    finally:
        doc.close()
