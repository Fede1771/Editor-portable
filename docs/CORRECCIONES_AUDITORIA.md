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

Validación del 23/10/2026: **121 pruebas aprobadas**, proceso terminado con código 0; las seis comprobaciones del EXE final también aprobaron. `pip check` no encontró dependencias incompatibles. La suite emite una advertencia de deprecación de `fitz` dentro de `pdf2docx`. La ejecución definitiva de pytest se hizo con temporales y preferencias aislados fuera del sandbox: allí no se reprodujeron los errores de permisos ni el fallo nativo al cerrar Qt observados en el entorno restringido.

## Alcance de seguridad

- El saneamiento se aplica al PDF principal. Los adjuntos se conservan y no se inspeccionan recursivamente.
- La detección de una firma aplicada no valida su certificado o confianza criptográfica. Las transformaciones que reescriben el PDF avisan de que pueden invalidarla.
- El modo privado evita recientes y mantiene Undo en RAM. Algunas conversiones requieren temporales físicos. La limpieza es de mejor esfuerzo; no se promete ausencia forense de rastros.
- Las pruebas no certifican ausencia de vulnerabilidades ni validan todos los formatos o versiones de dependencias admitidas.
