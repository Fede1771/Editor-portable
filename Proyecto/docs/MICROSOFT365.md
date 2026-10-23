# Conversiones con Microsoft 365 de escritorio

El editor usa las aplicaciones locales mediante COM y pywin32. No utiliza LibreOffice ni envía documentos a un servicio de conversión del editor. Los servicios y las políticas de Microsoft 365 son los de la instalación de la compañía.

## Motores utilizados

| Operación | Implementación |
|---|---|
| PDF → DOCX | Snapshot del PDF en vivo, reconstrucción local con pdf2docx, apertura del DOCX temporal con Word y `SaveAs2` al formato 16. |
| PDF → XLSX | Conector `Pdf.Tables` de Power Query en Excel. Se importan tablas o, si no hay tablas, los datos de página. Un libro nuevo recibe sólo los valores de texto y se guarda con formato 51. |
| Word → PDF | `Documents.Open` como sólo lectura y `ExportAsFixedFormat` al formato 17. |
| Excel → PDF | `Workbooks.Open` sin actualizar enlaces, sólo lectura, cálculo manual; `ExportAsFixedFormat` tipo 0. |
| PowerPoint → PDF | `Presentations.Open` como sólo lectura, sin ventana; `SaveAs` al formato 32. |

El importador directo de PDF de Word no completó las pruebas locales dentro de 120 segundos. El flujo publicado no lo utiliza: Word recibe un DOCX intermedio. La calidad de reconstrucción de un PDF sigue dependiendo de su estructura.

## Aislamiento y guardado

- Cada trabajo COM corre en un proceso creado con `multiprocessing.spawn`, inicializado como STA. Los objetos PDF y COM no se comparten entre hilos o procesos.
- Un mutex por aplicación serializa las conversiones entre distintas instancias del editor, incluyendo la activación de PowerPoint.
- Word y Excel se crean con `DispatchEx`. Se identifica la instancia creada antes de abrir el archivo de entrada. PowerPoint es MultiUse: si ya hay un proceso abierto se rechaza el trabajo antes de conectarse a él.
- Se solicita `AutomationSecurity = 3`, se desactivan eventos de Excel y se evita actualizar enlaces al abrir. No se alteran políticas del Centro de confianza ni se aceptan sus avisos. Excel 4.0/XLM puede requerir confirmación adicional aun con esa opción; un aviso o bloqueo puede terminar en timeout y error.
- Un timeout termina el trabajador. La limpieza de Office valida PID, hora de creación y nombre de la instancia registrada; nunca finaliza aplicaciones por nombre de forma global.
- La salida se escribe en un temporal del directorio de destino. Se valida antes de `os.replace`: contenido OOXML del DOCX, reapertura del XLSX sin fórmulas y estructura/páginas del PDF. Un fallo conserva el destino anterior.
- El XLSX final se crea en un libro separado del usado para Power Query. No se copian consultas, conexiones ni referencias al snapshot temporal. Las celdas se formatean como texto antes de asignar sus valores.
- Se ajustan anchos y saltos de línea del XLSX generado. La exportación de archivos Excel existentes a PDF respeta sus ajustes de impresión originales.
- Los snapshots y DOCX intermedios usan `TempManager`. Microsoft 365 puede generar cachés, recientes u otros temporales propios: el modo privado del editor no controla todos los rastros de Office.

## Dependencias

Se requieren Microsoft 365 de escritorio para Windows, activación válida y las aplicaciones correspondientes. Para PDF → XLSX también se necesita el conector PDF de Power Query. La versión web de Microsoft 365 no sustituye las aplicaciones locales.

`pywin32` y `psutil` se distribuyen con el portable. Microsoft 365 no se incluye en el ZIP. `openpyxl` se utiliza para verificar los XLSX y `pdf2docx` prepara el DOCX intermedio.

## Uso y diagnóstico

Para PDF → Word o Excel, abrí el PDF y elegí la aplicación de destino en **Exportar / Convertir a…**. La conversión incluye los cambios sin guardar del documento actual. Para Office → PDF, usá **Crear PDF desde archivos…** (`Ctrl + N`); el resultado se abre en una pestaña nueva que debés guardar con `Ctrl + S`.

| Problema | Qué revisar |
|---|---|
| No se inicia la aplicación de Office. | Abrila manualmente y comprobá su activación y que no esté esperando configuración inicial. La suscripción web no sustituye la instalación local. |
| PowerPoint ya está abierto. | Guardá tus presentaciones, cerrá PowerPoint y reintentá. |
| Excel no encuentra contenido tabular. | Comprobá que el PDF tenga texto seleccionable. Aplicá OCR si es un escaneo y revisá el texto reconocido. |
| Excel exporta un PDF con contenido recortado. | Revisá los anchos de columna, el área de impresión y la escala del archivo de origen. |
| La conversión supera el tiempo máximo. | Revisá contraseñas, avisos pendientes de Office y restricciones corporativas. Registrá el mensaje exacto si necesitás reportarlo. |

Para ejecutar las ocho comprobaciones del portable desde PowerShell en la raíz del repositorio:

```powershell
$env:PYINSTALLER_SUPPRESS_SPLASH_SCREEN = '1'
$prueba = Start-Process -FilePath '.\Programa\EditorPDFPortable\EditorPDFPortable.exe' `
    -ArgumentList '--self-test ".\Proyecto\diagnostico_runtime"' `
    -WindowStyle Hidden -Wait -PassThru
$prueba.ExitCode
Get-Content -LiteralPath '.\Proyecto\diagnostico_runtime\self_test_result.json'
```

La autoprueba requiere Word y Excel instalados y activados. Usa documentos sintéticos y preferencias del editor aisladas; no necesita escáner ni impresora. Devuelve código `0` si pasan todas las comprobaciones y guarda el detalle en el JSON indicado. Los archivos de diagnóstico se pueden eliminar después de revisarlos.

## Verificación del 23/10/2026

Entorno: Windows x64, CPython 3.14 y Microsoft 365 de escritorio, versión `16.0.20527.20088` (`O365ProPlusRetail`, x64).

- Suite completa: **204 pruebas aprobadas, salida 0**, con 11 casos nuevos de integración y protección ante fallos. Permanece una advertencia de deprecación de `fitz` dentro de pdf2docx.
- Cinco conversiones reales completadas: PDF → DOCX/XLSX y DOCX/XLSX/PPTX → PDF. Los resultados se reabrieron con python-docx, openpyxl y PyMuPDF para verificar contenido persistido. El XLSX conservó `=1+1` como texto y no incluyó fórmulas, conexiones, enlaces externos ni partes customXml.
- Portable regenerado: **8/8 comprobaciones, salida 0**. Comprueba procesos independientes, PDF → Word/Excel, retorno de ambos formatos a PDF, imágenes, compresión cifrada y OCR persistido. PowerPoint se verificó por separado desde el código fuente, no forma parte de estas ocho comprobaciones.
- El SHA-256 del EXE coincide con el incluido en el ZIP: `3230869b0a51056c9d184f503d693eeff0a0555f4dd39540cce1fefb952b156b`.
- `pip check` sin incompatibilidades; OSV sin avisos para las 41 versiones del lock en la consulta de esta fecha. Esto no certifica ausencia de vulnerabilidades ni compatibilidad con todas las instalaciones corporativas.

Las pruebas usan documentos sintéticos. La fidelidad de diseños complejos, el reconocimiento de escaneos y los permisos del Centro de confianza deben comprobarse con muestras representativas de la compañía.

## Referencias

- [Conector PDF de Power Query](https://learn.microsoft.com/en-us/power-query/connectors/pdf).
- [Seguridad de automatización de Excel y límite con macros XLM](https://learn.microsoft.com/en-us/office/vba/api/excel.application.automationsecurity).
- [Seguridad de automatización de PowerPoint](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.application.automationsecurity).
- [Instancias SingleUse y MultiUse de Office](https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/use-visual-c-automate-run-program-instance).
