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
| V03 | `ocr_document()` clona con `clone_pdf()` en vez de `selected_copy()`, conserva adjuntos de catálogo (`embfile_*`), conserva los objetos Page y sus referencias entrantes, enlaces y tabla de contenidos al reemplazar sólo su contenido, y `MainWindow.run_ocr()` advierte si las páginas seleccionadas contienen formularios o anotaciones no preservables. | Adjuntos, marcadores con páginas válidas y enlaces internos conservados tras OCR; detección previa de formularios y anotaciones. |
| V04 | `pypdf` actualizado a `6.21.2` en `requirements.txt` y `requirements.lock` (0 vulnerabilidades en OSV); `app/pdf_objects.py` impone límites de bytes (`MAX_OBJECT_BYTES`), profundidad (`MAX_OBJECT_DEPTH`), elementos (`MAX_OBJECT_ELEMENTS`) y nodos recorridos (`MAX_TRAVERSAL_NODES`) con `PdfObjectLimitError`. | Verificación de versión `>=6.21.1`, rechazo de objetos sobredimensionados/profundos/masivos y consulta OSV limpia sobre los 40 paquetes de `requirements.lock`. |
| V05 | `inspect_signatures()` y `document_has_signatures()` inspeccionan `page.widgets()`, el árbol canónico `/AcroForm/Fields` (incluyendo herencia de `/FT /Sig` y diccionarios `/V` de firma) y `/Catalog /Perms` (`/DocMDP`, `/UR`, `/UR3`), distinguiendo campos vacíos sin firmar de firmas aplicadas y dejando explícito que no realiza validación criptográfica de certificados. | Detección de firmas sin widget en página y en `/Perms`, sin falsos positivos en widgets `/FT /Sig` vacíos. |
| V06 | `AttachmentWidget.reload()` usa icono estándar de Qt (`SP_FileIcon`) y normaliza la etiqueta visible con `safe_local_name()`, sin pasar rutas del PDF a `QFileInfo` ni `QFileIconProvider`. | Rutas UNC (`\\198.51.100.10\...`), rutas Windows y ADS no invocan `QFileIconProvider.icon(QFileInfo)` y muestran nombres locales saneados. |
| V07 | `convert_to_excel()`, `convert_to_word()`, `convert_to_text()` y `convert_to_html()` escriben en un archivo temporal único en el mismo directorio, verifican la salida generada (incluyendo reapertura con `openpyxl.load_workbook` en `.xlsx` y validación ZIP en `.docx`), reemplazan con `os.replace()` y limpian el temporal en `finally`. | Fallo de E/S simulado a mitad del guardado preserva intacto byte a byte el `.xlsx`/`.txt` previo sin dejar temporales residuales. |
| V08 | `ThumbnailList._set_icon()` ajusta simultáneamente por ancho y alto (`THUMB_W x THUMB_H`) y presupuesto de píxeles (`MAX_THUMB_PIXELS`); `render_bounded_pixmap()` aplica límite de píxeles considerando `/UserUnit` en visor, OCR, exportación a imágenes e impresión; `ThumbnailList._fill_batch()` registra páginas fallidas sin reintentar en bucle infinito. | Página extrema `10 x 100000` renderizada dentro de `120 x 170` px y fallo inyectado en página 0 no reactiva indefinidamente el `QTimer`. |
| V09 | `update_form_fields()` escribe `/V` e `/I` en el campo terminal canónico (`terminal_field_owner()`), sin ascender a grupos de campos independientes, limpia `/V` e `/I` contradictorios en widgets hijos y sincroniza el stream de apariencia `/AP/N` en `ListBox` multiselección. | Lectura consistente de `["A", "C"]` e índices `[0, 2]` tanto en `get_form_fields()` como en `pypdf.PdfReader(out).get_fields()`. |
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

Validación de A01–A07 del 23/10/2026: **166 pruebas aprobadas, proceso terminado con código 0** (136 anteriores y 30 regresiones en `tests/test_correcciones_a01_a07.py`). Las 136 pruebas originales también se ejecutaron por separado con salida 0. La autoprueba del portable de esa revisión aprobó **6/6 comprobaciones, salida 0**, incluyendo OCR cifrado guardado y reabierto con geometría y texto verificados. `pip check` no encontró dependencias incompatibles. La advertencia de deprecación de `fitz` dentro de `pdf2docx` permanece. Las dependencias no se cambiaron; la consulta OSV de la reauditoría devolvió cero avisos para los 40 paquetes del lock, sin certificar ausencia de vulnerabilidades.

## Correcciones A01-A07 y cierre de pruebas

| ID | Cambio | Regresión y criterio |
|---|---|---|
| A01 | Normalización semántica HTML: spans inline se concatenan, párrafos y bloques se separan. Lectura iterativa de representaciones indirectas, UTF-16 y errores de inspección explícitos. | `/RV` y `/RC`, string/stream, spans dentro de párrafos; pypdf inspecciona los objetos y streams del resultado guardado. Un fallo de lectura impide declarar censura completa. |
| A02 | Resolvedor común del campo terminal y sus widgets. La edición y censura excluyen los grupos y campos hermanos. | Jerarquías de uno y dos niveles, ediciones consecutivas/conjuntas y preservación de datos y apariencia de otro terminal tras censurar. |
| A03 | Inspección previa del alcance de páginas. No se buscan ni limpian campos enteramente fuera del rango. Un terminal compartido entre páginas incluidas/excluidas se rechaza antes de modificar. | Cero coincidencias produce cero cambios; censura manual y por búsqueda rechazan el alcance parcial; incluir todas las páginas permite censurar el terminal compartido. |
| A04 | `/V` y `/AS` usan el estado real de `/AP/N` y codificación de nombres PDF. Sólo `/Off` desactiva un valor de exportación textual. | Secuencias marcar/desmarcar/marcar con `/Accepted`, `/No` y `/1`; pypdf verifica valor canónico, estado y apariencia tras reabrir. |
| A05 | El renderizado declara DPI efectivos. OCR conserva MediaBox, CropBox, Rotate, UserUnit y geometría colocando contenido reconocido en el Page original. | Tesseract real a 72/150/300 DPI; raster limitado, recortes y giros con marcadores visuales; resolución de PNG exportado y resultado persistido en autoprueba del portable. |
| A06 | OCR conserva la identidad del Page y el árbol de navegación, sin reconstrucción destructiva de enlaces o marcadores. Un error estructural descarta la copia en lugar de publicarla como reconocimiento parcial. | Enlace entrante desde página no procesada, URI en página OCR y marcador URI con estilo, comprobados al guardar y reabrir. |
| A07 | Ambos rasterizados de edición usan presupuesto de 65.536 píxeles. El cálculo incluye extremos absolutos y redondeo; el muestreo usa histograma ponderado, sin listas por píxel. | Bloque extremo y dos clips angostos desplazados: se verifica el presupuesto antes de asignar y en el Pixmap real. |
| O01 de reauditoría | La fixture de QApplication destruye ventanas, procesa DeferredDelete, recolecta ciclos y cierra Qt explícitamente antes de finalizar Python. No fuerza la salida del proceso ni oculta excepciones nativas. | La suite completa y la original deben terminar con salida 0; se exige no dejar ventanas nativas vivas. El símbolo exacto que originaba el abort previo no se atribuye sin dump nativo. |

La censura de un campo terminal compartido requiere incluir todas las páginas que lo representan. La política se aplica también a la censura rectangular; evita cambiar un valor lógico común mientras se pretende excluir otras páginas.

## Correcciones C01–C04 de la verificación precommit

| ID | Problema y corrección | Verificación independiente |
|---|---|---|
| C01 | La búsqueda omitía texto secreto de apariencias alternativas `/AP/R` y `/AP/D`. `AppearanceInspector` interpreta todos los estados N/R/D con MuPDF, en una copia aislada y con fuentes, matrices y recursos reales; incluye Forms anidados y recursos heredados sin sustituir sus XObjects. Apariencias estructuralmente inválidas impiden la operación antes de modificar el documento. | Texto hexadecimal, estados directos/diccionarios, Forms anidados y anotación FreeText. Tras guardar con recolección y reabrir con pypdf, no quedan el campo ni los streams con el secreto. En la reproducción original: 2 coincidencias eliminadas, 0 búsquedas visibles y ningún secreto en streams descomprimidos. |
| C02 | La limpieza borraba un stream de apariencia compartido por otro campo independiente. El recorrido estructural del catálogo identifica los recursos todavía utilizados fuera de los nodos afectados; se desvinculan las claves privadas y sólo se vacían objetos no compartidos. El reemplazo de texto utiliza las mismas protecciones y rechaza un terminal compartido con páginas excluidas. | Deduplicación real con `garbage=4`, censura por búsqueda/rectángulo y reemplazo. El AP/N ajeno conserva sus 84 bytes y BBox, además del valor PUBLIC. Render independiente con Poppler conserva PUBLIC y ya no presenta el error de Form sin BBox. |
| C03 | El saneador seguía referencias de destinos de navegación hacia Page/Annots y destruía acciones URI ajenas. El recorrido ahora distingue acciones, eventos, continuaciones `/Next` y árboles de nombres JavaScript. Primero inspecciona, después desvincula y finalmente limpia sólo acciones que no siguen alcanzables desde navegación preservada. | OpenAction como destino array o GoTo; URI directa/indirecta y continuación URI compartida. Los enlaces sobreviven al guardado/reapertura. JavaScript en Names/Kids desaparece sin alterar los bytes del adjunto. |
| C04 | Los radio buttons se editaban como texto y `/V` se persistía como TextStringObject. Se usan opciones explícitas en la GUI y escritura como NameObject, sincronizando `/AS` de todos los widgets. Se respetan NoToggleToOff y RadiosInUnison; estados duplicados sin Unison requieren seleccionar un widget inequívoco. Grupos no representables se muestran de sólo lectura con motivo. | pypdf verifica `/V /Yes` y estados exclusivos tras reabrir. También selección Off/Other, valores duplicados, Unison, rechazo con rollback, etiquetas `/Opt` y sincronización de los combos de la GUI. |

`tests/test_correcciones_c01_c04.py` agrega **27 casos**, incluyendo el reemplazo de texto que intersecta widgets y la inspección de XObjects heredados. La suite completa tiene **193 pruebas aprobadas, salida 0**. Las comprobaciones leen el resultado persistido con pypdf; el caso de apariencia compartida también se renderiza con Poppler. Los documentos originales utilizados para reproducir los problemas se conservaron.

El EXE y ZIP se regeneraron después de C01–C04. La autoprueba de ese ejecutable aprobó **6/6 comprobaciones con salida 0**: procesos independientes, Word, Excel, imágenes, compresión cifrada y OCR. El ZIP incluye el mismo EXE probado (comparación SHA-256). Las 27 regresiones específicas se ejecutan desde Python; la autoprueba empaquetada es una comprobación de integración y no sustituye esa suite.


## Alcance de seguridad

- El saneamiento se aplica al PDF principal. Los adjuntos se conservan y no se inspeccionan recursivamente.
- La detección de una firma aplicada no valida su certificado o confianza criptográfica. Las transformaciones que reescriben el PDF avisan de que pueden invalidarla.
- El modo privado evita recientes y mantiene Undo en RAM. Algunas conversiones requieren temporales físicos. La limpieza es de mejor esfuerzo; no se promete ausencia forense de rastros.
- Las pruebas no certifican ausencia de vulnerabilidades ni validan todos los formatos o versiones de dependencias admitidas.
