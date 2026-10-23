# Correcciones posteriores a la auditoría 7c0f34d

Las regresiones de `tests/test_revision_final.py` reproducen los problemas R01-R13 y O01 del informe. Las pruebas anteriores se conservan; la de concurrencia se actualizó para exigir un proceso independiente y la de residuos para exigir propiedad, antigüedad y PID terminado.

| Caso | Corrección | Comprobación |
| --- | --- | --- |
| R01 | Trabajos PDF explícitos con `multiprocessing.spawn`; sólo bytes y parámetros cruzan el límite del proceso. El hilo receptor sólo recibe IPC. | PID distinto y exportación desde `MainWindow` con cambios sin guardar; error del proceso y documento original intacto. |
| R02 | El pixmap reducido se dibuja dentro del rectángulo lógico completo. | Marca visible y coordenadas de edición coinciden al forzar el límite de píxeles. |
| R03 | Inspección estructural de claves y acciones PDF; se elimina sólo `Names/JavaScript`. | Tokens literales en descripciones no son scripts; anexos conservados con igual hash. |
| R04 | Snapshots y salidas PDF conservan cifrado con `PDF_ENCRYPT_KEEP`, también con contraseña de usuario vacía. Guardado derivado por temporal propio y verificación antes de reemplazar. | Editar/Undo/Redo, guardar, comprimir, anonimizar, extraer y dividir; comprobar método, permisos y texto al reabrir. |
| R05 | La censura inspecciona valores por defecto y datos heredados; limpia los padres lógicos. | `/DV` secreto directo y heredado no queda en el PDF reabierto. |
| R06 | Parser de cadenas PDF con escapes y UTF-16; escritura con codificación PDF válida. | Listas Unicode y caracteres escapados conservados al aceptar y reabrir. |
| R07 | Combo editable y valor vacío/personalizado conservados; etiquetas visibles separadas del valor de exportación. | Aceptar sin editar no sustituye el valor; etiquetas país no reemplazan sus códigos. |
| R08 | Conversión coherente de alfa premultiplicado entre MuPDF y QImage. | Reducción real de imágenes con alfa 0/64/128/192/255 y comparación de colores. |
| R09 | Límites de edición en espacio no rotado, igual que los bbox. | Reemplazo junto al borde en páginas 0/90/180/270 grados. |
| R10 | OCR devuelve estado por página y conserva la página original cuando falla. | Fallo conserva texto buscable; la GUI no abre una falsa pestaña reconocida. |
| R11 | La confirmación de censura se emite sólo después de una transacción exitosa. | Error inyectado sin diálogo de éxito ni cambios confirmados. |
| R12 | Temporales aislados con marca de propiedad, PID y antigüedad; recuperación al inicio; escáner y portapapeles usan el gestor. La UI describe las escrituras a disco necesarias. | Limpieza tras fallo de Word; residuos desconocidos y procesos activos conservados; modo privado propagado al trabajador. |
| R13 | Escáner y saneamiento comparten la clasificación de acciones; XFA requiere una decisión explícita antes de eliminarse. | Acciones Sound/Movie/Rendition detectadas; XFA bloquea por defecto y se elimina sólo con autorización. |
| O01 | Rollback del helper restaura diccionarios completos y streams de apariencia anteriores. | `/V`, `/I` y `/AP` conservados al fallar el segundo campo. |

## Correcciones posteriores a la revisión integral cb8b57b (V01–V09 y O01–O03)

Las regresiones de `tests/test_verificacion_v01_v09.py` verifican los hallazgos V01–V09 y observaciones O01–O03 con comprobadores independientes del escáner/lector de producción:

| Caso | Corrección | Comprobación |
| --- | --- | --- |
| V01 | `_action_locations()` recorre el árbol `/Outlines` (`First`/`Last`/`Next`/`Prev`), `PresSteps` de página y `/AcroForm/Fields` sin widget. `sanitize_document()` conserva navegación segura (`/URI`, `/GoTo`, `/Named`), corta continuaciones activas `A/Next` y neutraliza objetos indirectos de acción. | Marcadores con `/JavaScript` y `/URI` + `/Next /Launch`, además de campos fuera de página, detectados y eliminados sin rastros en bytes crudos ni objetos `xref`. |
| V02 | `redact_search_phrase()` y `apply_redaction()` inspeccionan `/RV`, `/RC`, `/DS`, `/TU`, `/TM`, `/Opt`, `/Contents`, `/T`, `/Subj` y `/Popup` como cadenas o streams, decodificando entidades HTML y XHTML fragmentado, resuelven familias lógicas de campos antes de mutar y exigen decisión explícita sobre `AcroForm/XFA`. | Secretos en `/RV` (stream con entidades y XHTML fragmentado), familias `Parent`/`Kids`, `/RC` (stream) y `XFA` eliminados verificando ausencia total en bytes crudos y streams descomprimidos. |
| V03 | `ocr_document()` clona con `clone_pdf()` en vez de `selected_copy()`, conserva adjuntos de catálogo (`embfile_*`), reconstruye enlaces (`LINK_GOTO`, `LINK_URI`, `LINK_NAMED`) y tabla de contenidos (`get_toc(simple=False)` -> `set_toc()`), y `MainWindow.run_ocr()` advierte si las páginas seleccionadas contienen formularios o anotaciones no preservables. | Adjuntos, marcadores con páginas válidas y enlaces internos conservados tras OCR; detección previa de formularios y anotaciones. |
| V04 | `pypdf` actualizado a `6.21.2` en `requirements.txt` y `requirements.lock` (0 vulnerabilidades en OSV); `app/pdf_objects.py` impone límites de bytes (`MAX_OBJECT_BYTES`), profundidad (`MAX_OBJECT_DEPTH`), elementos (`MAX_OBJECT_ELEMENTS`) y nodos recorridos (`MAX_TRAVERSAL_NODES`) con `PdfObjectLimitError`. | Verificación de versión `>=6.21.1`, rechazo de objetos sobredimensionados/profundos/masivos y consulta OSV limpia sobre los 40 paquetes de `requirements.lock`. |
| V05 | `inspect_signatures()` y `document_has_signatures()` inspeccionan `page.widgets()`, el árbol canónico `/AcroForm/Fields` (incluyendo herencia de `/FT /Sig` y diccionarios `/V` de firma) y `/Catalog /Perms` (`/DocMDP`, `/UR`, `/UR3`), distinguiendo campos vacíos sin firmar de firmas aplicadas y dejando explícito que no realiza validación criptográfica de certificados. | Detección de firmas sin widget en página y en `/Perms`, sin falsos positivos en widgets `/FT /Sig` vacíos. |
| V06 | `AttachmentWidget.reload()` usa icono estándar de Qt (`SP_FileIcon`) y normaliza la etiqueta visible con `safe_local_name()`, sin pasar rutas del PDF a `QFileInfo` ni `QFileIconProvider`. | Rutas UNC (`\\198.51.100.10\...`), rutas Windows y ADS no invocan `QFileIconProvider.icon(QFileInfo)` y muestran nombres locales saneados. |
| V07 | `convert_to_excel()`, `convert_to_word()`, `convert_to_text()` y `convert_to_html()` escriben en un archivo temporal único en el mismo directorio, verifican la salida generada (incluyendo reapertura con `openpyxl.load_workbook` en `.xlsx` y validación ZIP en `.docx`), reemplazan con `os.replace()` y limpian el temporal en `finally`. | Fallo de E/S simulado a mitad del guardado preserva intacto byte a byte el `.xlsx`/`.txt` previo sin dejar temporales residuales. |
| V08 | `ThumbnailList._set_icon()` ajusta simultáneamente por ancho y alto (`THUMB_W x THUMB_H`) y presupuesto de píxeles (`MAX_THUMB_PIXELS`); `render_bounded_pixmap()` aplica límite de píxeles considerando `/UserUnit` en visor, OCR, exportación a imágenes e impresión; `ThumbnailList._fill_batch()` registra páginas fallidas sin reintentar en bucle infinito. | Página extrema `10 x 100000` renderizada dentro de `120 x 170` px y fallo inyectado en página 0 no reactiva indefinidamente el `QTimer`. |
| V09 | `update_form_fields()` escribe `/V` e `/I` en el campo propietario canónico (`chain[-1]`), limpia `/V` e `/I` contradictorios en widgets hijos y sincroniza el stream de apariencia `/AP/N` en `ListBox` multiselección. | Lectura consistente de `["A", "C"]` e índices `[0, 2]` tanto en `get_form_fields()` como en `pypdf.PdfReader(out).get_fields()`. |
| O01 | `normalize_field_value()` normaliza valores de `CheckBox`, `ListBox` y `Choice` antes de comparar cambios en `MainWindow.fill_form_fields()`. | Aceptar `FillFormsDialog` sin cambios no marca el documento como modificado ni altera casillas desmarcadas (`"Off"`). |
| O02 | `SafeLinkDialog._copy_url()` y `PdfView` (`Ctrl+C`) delegan en `privacy.copy_to_clipboard()` para registrar propiedad del portapapeles. | `clear_app_clipboard_if_owned()` limpia el texto/URL copiado al cerrar sesión privada. |
| O03 | `FillFormsDialog` envuelve el formulario en un `QScrollArea` (`setWidgetResizable(True)`) y acota `sizeHint()` y `maximumHeight()` a la altura disponible de pantalla (`<= 680 px`). | Con 60 campos, el diálogo mantiene `sizeHint().height() <= 680` px y desplazamiento vertical funcional. |

También se centralizó la confirmación de reescritura de documentos firmados para guardar, comprimir, anonimizar, OCR y extracción/división (incluido el menú de miniaturas). Una selección de texto con estilos distintos requiere aceptar su conversión a formato único.

El empaquetado aísla el `PATH` usado para resolver DLLs. Se reprodujo un fallo de inicio causado por una `icuuc.dll` de Poppler tomada de herramientas externas: su ABI no coincide con la ICU de Windows requerida por Qt. El portable se vuelve a comprobar después de compilar, además de ejecutar las pruebas desde Python.

## Ejecutar y comprobar

El entorno de versiones exactas probado es Windows x64 con CPython 3.14:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe build_portable.py
```

`requirements.txt` contiene dependencias de ejecución. `requirements-dev.txt` agrega pruebas y empaquetado; `requirements.lock` fija las versiones del entorno completo probado. El lock no contiene hashes de los wheels ni sustituye una revisión de vulnerabilidades de terceros.

Para comprobar el runtime empaquetado sin abrir documentos reales:

```powershell
$env:PYINSTALLER_SUPPRESS_SPLASH_SCREEN = '1'
.\dist\EditorPDFPortable\EditorPDFPortable.exe --self-test .\diagnostico_runtime
```

El resultado se escribe en `self_test_result.json`. La prueba crea documentos sintéticos, usa preferencias aisladas y comprueba procesos independientes, Word, Excel, imágenes, compresión cifrada y OCR. Los archivos de diagnóstico se pueden eliminar después de revisar el resultado. Esta comprobación no requiere Microsoft Office, escáner ni impresora.

Validación del 23/10/2026: **136 pruebas aprobadas** (incluyendo las 15 pruebas de `tests/test_verificacion_v01_v09.py`), proceso terminado con código 0; las seis comprobaciones del EXE final también aprobaron. `pip check` no encontró dependencias incompatibles y la consulta a OSV para los 40 paquetes de `requirements.lock` devolvió **0 vulnerabilidades**. La suite emite una advertencia de deprecación de `fitz` dentro de `pdf2docx`. La ejecución definitiva de pytest se hizo con temporales y preferencias aislados fuera del sandbox: allí no se reprodujeron los errores de permisos ni el fallo nativo al cerrar Qt observados en el entorno restringido.

## Alcance de seguridad

- El saneamiento se aplica al PDF principal. Los adjuntos se conservan y no se inspeccionan recursivamente.
- La detección de una firma aplicada no valida su certificado o confianza criptográfica. Las transformaciones que reescriben el PDF avisan de que pueden invalidarla.
- El modo privado evita recientes y mantiene Undo en RAM. Algunas conversiones requieren temporales físicos. La limpieza es de mejor esfuerzo; no se promete ausencia forense de rastros.
- Las pruebas no certifican ausencia de vulnerabilidades ni validan todos los formatos o versiones de dependencias admitidas.
