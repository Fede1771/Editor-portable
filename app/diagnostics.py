"""Prueba local del runtime empaquetado: sin documentos del usuario ni red."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import traceback


def self_test(output_dir: str) -> int:
    import pymupdf as fitz
    from PySide6.QtWidgets import QApplication
    from .background import run_pdf_job
    from .document_io import open_pdf
    from .main_window import MainWindow
    from .privacy import TempManager

    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="runtime_check_", dir=root))
    os.environ["EDITORPDF_SETTINGS_DIR"] = str(work / "settings")
    app = QApplication.instance() or QApplication([])
    result = {"ok": False, "checks": {}, "work": str(work)}
    win = None
    doc = None
    try:
        win = MainWindow()
        source = fitz.open()
        source.new_page(width=400, height=300).insert_text((30, 70), "PORTABLE_RUNTIME_CHECK", fontsize=18)
        raw = source.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="test-user", owner_pw="test-owner")
        source.close()
        doc = open_pdf(raw, "test-user")
        inspected = run_pdf_job(win, "Verificando procesos…", "inspect", doc)
        assert inspected["pid"] != os.getpid() and "PORTABLE_RUNTIME_CHECK" in inspected["text"]
        result["checks"]["independent_process"] = True
        for operation, output in (("word", work / "export.docx"), ("excel", work / "export.xlsx")):
            run_pdf_job(win, "Verificando exportación…", operation, doc, str(output))
            assert output.stat().st_size > 0
            result["checks"][operation] = True
        files = run_pdf_job(win, "Verificando imágenes…", "images", doc, str(work / "images"), dpi=72)
        assert len(files) == 1 and Path(files[0]).is_file()
        result["checks"]["images"] = True
        out = work / "compressed.pdf"
        run_pdf_job(win, "Verificando cifrado y saneamiento…", "optimize", doc, str(out), sanitize_metadata=True)
        with open_pdf(out.read_bytes(), "test-user") as check:
            assert check.metadata["encryption"] == doc.metadata["encryption"]
            assert "PORTABLE_RUNTIME_CHECK" in check[0].get_text()
        result["checks"]["encrypted_compression"] = True
        recognized = run_pdf_job(win, "Verificando OCR…", "ocr", doc, language="eng", dpi=150)
        try:
            assert recognized._editorpdf_ocr_report["recognized"] == [1]
            assert recognized.metadata["encryption"] == doc.metadata["encryption"]
        finally:
            recognized.close()
        result["checks"]["ocr"] = True
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if doc is not None:
            doc.close()
        if win is not None:
            win.close()
        TempManager.cleanup_all()
        (root / "self_test_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
