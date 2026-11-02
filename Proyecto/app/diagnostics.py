"""Prueba local del runtime empaquetado: sin documentos del usuario ni red."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import traceback


def office_self_test(output_dir: str) -> int:
    """Diagnóstico optativo de Word real; sólo usa un DOCX sintético propio."""
    import zipfile
    import pymupdf as fitz
    from .creation import office_to_pdf_file
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="office_check_", dir=root))
    result = {"ok": False, "checks": {}, "work": str(work)}
    marker = "WORD_PDF_RUNTIME_CHECK"
    source = work / "Prueba Word.docx"
    try:
        # Paquete OOXML mínimo, sin macros, vínculos ni archivos del usuario.
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>'
            ))
            package.writestr("_rels/.rels", (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '</Relationships>'
            ))
            package.writestr("word/document.xml", (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body><w:p><w:r><w:t>{marker}</w:t></w:r></w:p>'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
            ))
        before = source.read_bytes()
        target = office_to_pdf_file(str(source), str(work))
        with fitz.open(target) as pdf:
            if len(pdf) != 1 or marker not in pdf[0].get_text():
                raise ValueError("El PDF exportado no contiene el texto de prueba de Word.")
        if source.read_bytes() != before:
            raise ValueError("Word modificó el documento de origen.")
        result["checks"]["word_pdf"] = True
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    (root / "office_self_test_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def self_test(output_dir: str) -> int:
    import pymupdf as fitz
    from PySide6.QtWidgets import QApplication
    from .background import run_pdf_job, run_blocking
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
            assert recognized[0].rect == doc[0].rect
            assert recognized[0].rotation == doc[0].rotation
            # Verificar el resultado persistido, no sólo el documento en RAM.
            from .document_io import save_pdf
            saved_ocr = work / "recognized.pdf"
            save_pdf(recognized, str(saved_ocr), garbage=4)
            with open_pdf(saved_ocr.read_bytes(), "test-user") as check:
                assert check[0].rect == doc[0].rect
                assert "PORTABLE_RUNTIME_CHECK" in check[0].get_text()
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
