"""
Suite de pruebas automatizadas para Editor PDF Portable.
Ejecuta validaciones integrales de operaciones, edición in situ, creación, OCR, conversión y optimización.
"""
import sys
import os
import warnings
from pathlib import Path

# Suprimir advertencia transitoria de la API clásica de PyMuPDF
warnings.filterwarnings("ignore", category=FutureWarning, module=r"fitz(\..*)?")
warnings.filterwarnings("ignore", message=r".*The `fitz` API is deprecated.*", category=FutureWarning)

# Agregar raíz al sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf as fitz
from app import operations, creation, content_ops, ocr, conversion, optimizer, annotations, forms

def main():
    print("=== INICIANDO SUITE DE PRUEBAS DE EDITOR PDF ===")
    out_dir = ROOT / "tests" / "temp_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Creación
    print("[1/6] Probando creación...")
    doc = creation.blank_document(pages=2)
    p0 = doc[0]
    p0.insert_text((50, 80), "Documento de Prueba", fontsize=18)
    p0.insert_text((50, 120), "Texto original para editar", fontsize=12)
    p1 = doc[1]
    p1.insert_text((50, 80), "Segunda pagina con tabla y datos", fontsize=12)
    p1.insert_text((50, 120), "Columna1\tColumna2\nDato1\tDato2", fontsize=10)
    pdf_path = out_dir / "base.pdf"
    doc.save(str(pdf_path))
    doc.close()
    assert pdf_path.exists(), "Fallo guardado de base.pdf"
    print("  -> Creacion OK")

    # 2. Operaciones de página
    print("[2/6] Probando operaciones de pagina...")
    doc = fitz.open(str(pdf_path))
    operations.rotate_pages(doc, [0], 90)
    operations.duplicate_pages(doc, [0])
    assert len(doc) == 3, f"Esperaba 3 paginas, hay {len(doc)}"
    operations.delete_pages(doc, [2])
    assert len(doc) == 2, f"Esperaba 2 paginas tras delete, hay {len(doc)}"
    operations.add_watermark(doc, [0, 1], "CONFIDENCIAL", size=40, color=(0.8, 0.2, 0.2), opacity=0.3, angle=45)
    operations.add_header_footer(doc, [0, 1], template="Reporte - Pag {n}/{total}", position="Abajo al centro", size=10, start_number=1, bates_digits=4)
    doc.save(str(out_dir / "operado.pdf"))
    doc.close()
    print("  -> Operaciones OK")

    # 3. Edicion in situ y contenido
    print("[3/6] Probando edicion in situ...")
    doc = fitz.open(str(pdf_path))
    block = content_ops.find_text_block_at(doc[0], fitz.Point(60, 120))
    assert block is not None, "No se detecto el bloque de texto en (60, 120)"
    content_ops.replace_text_block(
        doc, 0, block["bbox"], "Texto modificado exitosamente",
        fontsize=block["fontsize"], fontname=block["fontname"], color=block["color"]
    )
    text_after = doc[0].get_text()
    assert "Texto modificado exitosamente" in text_after, "Texto modificado no se encontro en el PDF"
    assert "Texto original para editar" not in text_after, "Texto original no fue tapado limpiamente"
    doc.save(str(out_dir / "editado.pdf"))
    doc.close()
    print("  -> Edicion in situ OK")

    # 4. OCR
    print("[4/6] Probando OCR integrado...")
    doc = fitz.open(str(pdf_path))
    # Generar pagina rasterizada simulando escaneo
    pix = doc[0].get_pixmap(dpi=150)
    scan_doc = fitz.open()
    scan_page = scan_doc.new_page(width=pix.width, height=pix.height)
    scan_page.insert_image(scan_page.rect, stream=pix.tobytes("png"))
    
    ocr_doc = ocr.ocr_document(scan_doc, language="spa+eng", dpi=150)
    ocr_text = ocr_doc[0].get_text()
    assert len(ocr_text.strip()) > 0, "OCR no genero capa de texto"
    ocr_doc.save(str(out_dir / "ocr_resultado.pdf"))
    ocr_doc.close()
    scan_doc.close()
    doc.close()
    print(f"  -> OCR OK (reconocio {len(ocr_text.split())} palabras)")

    # 5. Conversiones
    print("[5/6] Probando conversiones...")
    doc = fitz.open(str(pdf_path))
    txt_path = out_dir / "export.txt"
    conversion.convert_to_text(doc, str(txt_path))
    assert txt_path.exists() and txt_path.stat().st_size > 0, "Fallo export txt"

    html_path = out_dir / "export.html"
    conversion.convert_to_html(doc, str(html_path))
    assert html_path.exists(), "Fallo export html"

    docx_path = out_dir / "export.docx"
    conversion.convert_to_word(doc, str(docx_path), src_path=str(pdf_path))
    assert docx_path.exists() and docx_path.stat().st_size > 0, "Fallo export docx"

    xlsx_path = out_dir / "export.xlsx"
    conversion.convert_to_excel(doc, str(xlsx_path))
    assert xlsx_path.exists(), "Fallo export xlsx"

    img_dir = out_dir / "imagenes"
    conversion.convert_to_images(doc, str(img_dir), fmt="png", dpi=100)
    assert len(list(img_dir.glob("*.png"))) == 2, "Fallo export imagenes"
    doc.close()
    print("  -> Conversiones OK")

    # 6. Optimizacion
    print("[6/6] Probando optimizacion...")
    doc = fitz.open(str(pdf_path))
    orig_sz, new_sz, saving = optimizer.optimize_document(
        doc,
        str(out_dir / "optimizado.pdf"),
        compress_images=True,
        image_quality=75,
        max_dpi=150,
        sanitize_metadata=True,
    )
    doc.close()
    assert Path(out_dir / "optimizado.pdf").exists(), "Fallo optimizacion"
    print(f"  -> Optimizacion OK ({orig_sz} bytes -> {new_sz} bytes, ahorro: {saving:.1f}%)")

    # 7. Anotaciones, comentarios y tinta
    print("[7/8] Probando comentarios, anotaciones y tinta...")
    doc = fitz.open(str(pdf_path))
    annotations.add_ink_annotation(doc, 0, [[(50.0, 50.0), (70.0, 60.0), (90.0, 50.0)]], author="Firma")
    annotations.add_note_annotation(doc, 0, fitz.Point(100, 100), "Comentario de revisión importante", author="Auditor")
    annotations.add_highlight_annotation(doc, 0, [fitz.Rect(50, 80, 200, 100)], author="Auditor", comment="Resaltado clave")
    annotations.add_underline_annotation(doc, 1, [fitz.Rect(50, 80, 200, 100)], author="Auditor")
    annotations.add_strikeout_annotation(doc, 1, [fitz.Rect(50, 120, 200, 140)], author="Auditor")

    all_comments = annotations.get_all_comments_and_annots(doc)
    assert len(all_comments) == 5, f"Esperaba 5 anotaciones/comentarios, obtuve {len(all_comments)}"
    assert any(c["author"] == "Auditor" for c in all_comments), "No se encontró comentario con autor Auditor"
    assert any("Comentario de revisión" in c["content"] for c in all_comments), "No se encontró el texto del comentario"
    doc.save(str(out_dir / "anotaciones.pdf"))
    doc.close()
    print(f"  -> Anotaciones y Comentarios OK ({len(all_comments)} anotaciones registradas)")

    # 8. Formularios AcroForms y aplanado
    print("[8/8] Probando formularios y aplanado (AcroForms)...")
    doc = fitz.open()
    p = doc.new_page()
    w1 = fitz.Widget()
    w1.rect = fitz.Rect(50, 50, 200, 75)
    w1.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w1.field_name = "Cliente"
    w1.field_value = "Original"
    p.add_widget(w1)

    w2 = fitz.Widget()
    w2.rect = fitz.Rect(50, 90, 70, 110)
    w2.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w2.field_name = "Aceptado"
    w2.field_value = False
    p.add_widget(w2)

    fields = forms.get_form_fields(doc)
    assert len(fields) == 2, f"Esperaba 2 campos de formulario, obtuve {len(fields)}"
    forms.update_form_fields(doc, {"Cliente": "Juan Carlos", "Aceptado": True})
    fields_updated = forms.get_form_fields(doc)
    assert fields_updated[0]["value"] == "Juan Carlos", "Valor de texto no se actualizó"
    assert fields_updated[1]["value"] in (True, "Yes", "On"), "Valor de checkbox no se actualizó"

    # Aplanar formulario
    forms.flatten_forms(doc)
    fields_after_flatten = forms.get_form_fields(doc)
    assert len(fields_after_flatten) == 0, "Los formularios debieron ser aplanados a contenido estático"
    doc.close()
    print("  -> Formularios y Aplanado OK")

    # 9. Archivos adjuntos embebidos (Attachments)
    print("[9/10] Probando gestión de archivos adjuntos embebidos...")
    from app import attachments as att_mod
    doc = fitz.open()
    doc.new_page()
    doc.embfile_add("adjunto_test.txt", b"Contenido de prueba embebido", filename="adjunto_test.txt", ufilename="adjunto_test.txt", desc="Archivo de prueba")
    assert doc.embfile_count() == 1, "Debería haber 1 archivo adjunto"
    atts = att_mod.get_all_attachments(doc)
    assert len(atts) == 1, "get_all_attachments debería retornar 1 adjunto"
    assert atts[0]["filename"] == "adjunto_test.txt"
    data = att_mod.get_attachment_bytes(doc, atts[0])
    assert data == b"Contenido de prueba embebido", "El contenido del adjunto no coincide"
    doc.embfile_del(0)
    assert doc.embfile_count() == 0, "El adjunto debió ser eliminado"
    doc.close()
    print("  -> Archivos Adjuntos OK")

    # 10. Módulo de Seguridad y Anti-Phishing
    print("[10/10] Probando módulo de seguridad, sanitización y anti-phishing...")
    from app import security as sec_mod
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"author": "Usuario Privado", "creator": "App Interna", "title": "Confidencial"})
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "OpenAction", "<< /S /Launch /F (powershell.exe) >>")

    sec_info = sec_mod.scan_document_security(doc)
    assert sec_info["has_threats"] is True, "El escáner de seguridad debió detectar la amenaza OpenAction"
    assert sec_info["has_launch"] is True, "Debió detectar acción /Launch"

    # Sanitizar
    cleaned = sec_mod.sanitize_document(doc)
    assert cleaned >= 1, f"Debió sanitizar al menos 1 elemento, limpió {cleaned}"
    sec_info_after = sec_mod.scan_document_security(doc)
    assert sec_info_after["has_threats"] is False, "Tras sanitizar no deben quedar amenazas"

    # Sanitizar metadatos
    sec_mod.sanitize_metadata(doc)
    assert doc.metadata["author"] == "", "El autor debió ser eliminado"
    assert doc.metadata["title"] == "", "El título debió ser eliminado"

    # Comprobación de URLs anti-phishing
    safe_check = sec_mod.check_url_safety("https://buenosaires.gob.ar/tramites")
    assert safe_check["is_safe"] is True, "URL legítima debió ser segura"

    suspicious_check = sec_mod.check_url_safety("http://192.168.1.50/update.exe")
    assert suspicious_check["is_safe"] is False, "URL con IP directa y .exe debió ser marcada como sospechosa"

    spoofed_check = sec_mod.check_url_safety("https://sitio-malicioso.com", visible_text="afip.gob.ar")
    assert spoofed_check["is_safe"] is False, "URL suplantada debió ser detectada como spoofing"
    doc.close()
    print("  -> Seguridad, Sanitización y Anti-Phishing OK")

    # 11. Snapshots de memoria y vuelco a disco para Undo/Redo
    print("[11/11] Probando snapshots de memoria y volcado a disco en Undo/Redo...")
    from app.doc_tab import _DocSnapshot
    # Prueba en memoria (<15MB)
    small_data = b"%PDF-1.4 test data in memory"
    snap_mem = _DocSnapshot(small_data)
    assert snap_mem._temp_path is None, "Snapshot pequeño debió permanecer en RAM"
    assert snap_mem.get_bytes() == small_data
    snap_mem.cleanup()

    # Prueba con umbral superado (simulamos temporalmente umbral bajo)
    orig_thresh = _DocSnapshot.DISK_THRESHOLD
    try:
        _DocSnapshot.DISK_THRESHOLD = 50  # forzar volcado con > 50 bytes
        big_data = b"%PDF-1.4 " + (b"X" * 100)
        snap_disk = _DocSnapshot(big_data)
        assert snap_disk._temp_path is not None, "Snapshot grande debió volcarse a disco"
        temp_file = snap_disk._temp_path
        assert os.path.isfile(temp_file), "Archivo temporal debió ser creado en disco"
        assert snap_disk.get_bytes() == big_data, "Los bytes leídos desde disco deben coincidir"
        snap_disk.cleanup()
        assert not os.path.exists(temp_file), "Archivo temporal debió ser eliminado en cleanup"
    finally:
        _DocSnapshot.DISK_THRESHOLD = orig_thresh
    print("  -> Snapshots y Gestión Eficiente de Memoria OK")

    # Limpieza de temporales de prueba
    import shutil
    shutil.rmtree(out_dir, ignore_errors=True)

    print("\nTODAS LAS PRUEBAS COMPLETADAS CON EXITO.")

if __name__ == "__main__":
    main()
