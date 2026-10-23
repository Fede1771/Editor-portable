# Editor PDF Portable

**Editor de PDF para Windows de 64 bits, con procesamiento local y OCR en español e inglés.**

Permite leer, editar, organizar, censurar y convertir documentos desde una interfaz con pestañas. La versión portable funciona sin instalar Python y se puede llevar en una carpeta o pendrive.

**[Descargar el ZIP de la última versión publicada](https://github.com/Fede1771/Editor-portable/releases/latest/download/EditorPDFPortable.zip)** · [Ver versiones publicadas](https://github.com/Fede1771/Editor-portable/releases)

[Inicio](#empezar-a-usarlo) · [Requisitos](#requisitos) · [Conversiones](#convertir-documentos) · [Problemas frecuentes](#problemas-frecuentes) · [Desarrollo](#desarrollo)

La lectura, edición y el OCR de PDF funcionan sin Microsoft 365. Las conversiones entre PDF y formatos Office requieren las aplicaciones de Microsoft 365 de escritorio instaladas en el equipo de destino; no se incluyen dentro del portable.

## Empezar a usarlo

### Si descargaste el portable

1. Descargá `EditorPDFPortable.zip` desde las versiones publicadas.
2. Elegí **Extraer todo…** y conservá completa la carpeta extraída.
3. Abrí `EditorPDFPortable.exe` o `Abrir_EditorPortable.bat`.
4. Arrastrá un PDF a la ventana o usá `Ctrl + O`.

La carpeta `_internal/` debe permanecer junto al ejecutable: contiene las bibliotecas y los recursos necesarios para funcionar.

### Si estás en esta carpeta de trabajo

Hacé doble clic en **`Abrir_EditorPortable.bat`**. El acceso abre el ejecutable de `Programa/EditorPDFPortable/`.

```text
Editor portable/
├── Abrir_EditorPortable.bat    Abrir el editor
├── README.md                  Esta guía
├── Programa/                  Ejecutable y ZIP para entregar
└── Proyecto/                  Código, herramientas, pruebas y documentación
```

`Programa/` se genera al compilar y no se incluye en Git. Si descargaste únicamente el código fuente, seguí los pasos de desarrollo y compilación de este documento.

## Qué podés hacer

| Función | Operaciones disponibles |
|---|---|
| Lectura y búsqueda | Abrir PDFs en pestañas, navegar con miniaturas, ajustar zoom, buscar y copiar texto. |
| Edición de contenido | Reemplazar bloques de texto e insertar texto, imágenes y enlaces. |
| Anotaciones | Resaltar, subrayar, tachar, dibujar y agregar notas o comentarios. |
| Censura | Eliminar contenido mediante un rectángulo o una búsqueda de texto. |
| Páginas | Combinar, insertar, extraer, duplicar, reordenar, rotar, recortar, eliminar y dividir documentos. |
| Presentación | Agregar marcas de agua, fondos, encabezados, pies y numeración. |
| Formularios | Completar campos AcroForm, casillas, listas y grupos de selección; aplanar formularios. |
| Compresión | Aplicar perfiles de calidad y resolución para reducir el tamaño de un PDF. |
| OCR | Convertir páginas escaneadas en PDFs con texto buscable, con modelos locales de español e inglés. |
| Exportación | Generar Word (`.docx`), Excel (`.xlsx`), PNG/JPEG, texto plano y HTML. |
| Adjuntos | Ver, agregar, extraer y eliminar archivos embebidos. |
| Creación | Crear PDFs desde imágenes, texto, HTML, archivos Office y escáneres compatibles. |

La fidelidad de la edición y las conversiones depende de las fuentes y de la estructura del documento. La reducción de tamaño depende de su contenido y del perfil elegido. En documentos escaneados, aplicá OCR antes de buscar texto.

## Requisitos

| Uso | Requisito |
|---|---|
| Ejecutar el portable | Windows de 64 bits y la carpeta extraída completa. |
| Exportar PDF a Word | Microsoft Word de escritorio instalado y activado, incluido en Microsoft 365. |
| Exportar PDF a Excel | Microsoft Excel de escritorio con el conector PDF de Power Query, incluido en Microsoft 365 para Windows. |
| Crear PDF desde Word, Excel o PowerPoint | La aplicación correspondiente de Microsoft 365 de escritorio instalada y activada. |
| Crear PDF desde un escáner | Escáner y controlador compatibles con WIA en Windows. |
| Trabajar con el código | Entorno probado: Windows x64 y CPython 3.14. |

### Integración con Microsoft 365

Las conversiones usan las aplicaciones instaladas en el equipo. La suscripción web por sí sola no proporciona la automatización de escritorio.

- **PDF → Word:** se reconstruye el contenido en un DOCX temporal y Word genera y guarda el archivo final. Word recibe ese DOCX intermedio, en lugar de abrir el PDF directamente.
- **PDF → Excel:** Power Query interpreta el PDF y Excel genera un libro final con valores de texto, sin fórmulas ni conexiones al PDF temporal.
- **Word / Excel / PowerPoint → PDF:** se utiliza la exportación nativa de la aplicación correspondiente, abriendo el archivo de origen como sólo lectura.

Las conversiones tienen un tiempo máximo y validan la salida antes de reemplazar el archivo de destino. Si PowerPoint ya está abierto, hay que cerrarlo antes de convertir una presentación para evitar utilizar su instancia compartida.

La exportación de archivos Excel existentes a PDF respeta sus anchos de columna y su configuración de impresión. Revisá esos ajustes en Excel si el documento ya se muestra recortado allí.

Más información en la [guía técnica de Microsoft 365](Proyecto/docs/MICROSOFT365.md).

## Convertir documentos

### De PDF a Word o Excel

1. Abrí el PDF y realizá los cambios que necesites. La exportación utiliza el documento actual, incluidos los cambios todavía sin guardar.
2. En el menú principal, elegí **Exportar / Convertir a… → Microsoft Word (.docx)…** o **Microsoft Excel (.xlsx)…**.
3. Elegí dónde guardar el archivo y esperá a que termine la conversión.
4. Abrí el resultado en Word o Excel y revisá el contenido y la distribución antes de entregarlo.

Excel está orientado a extraer tablas: las celdas se guardan como texto literal para conservar los datos del PDF sin evaluarlos como fórmulas. Si el documento es un escaneo, aplicá OCR antes de exportar.

### De Word, Excel o PowerPoint a PDF

1. Usá **Crear PDF → Crear PDF desde archivos…** o `Ctrl + N`.
2. Seleccioná los archivos Office. Si agregás varios, revisá su orden en el diálogo de combinación.
3. Confirmá la creación. El resultado se abre en una pestaña nueva del editor.
4. Guardá el PDF con `Ctrl + S`.

El editor abre los archivos Office de origen como sólo lectura. Además de `.docx`, `.xlsx` y `.pptx`, admite `.doc`, `.xls`, `.ppt`, `.rtf`, `.odt`, `.ods` y `.odp` mediante la aplicación correspondiente; la fidelidad depende de su compatibilidad con ese formato.

## Problemas frecuentes

| Qué ocurre | Qué revisar |
|---|---|
| No se puede iniciar Word, Excel o PowerPoint. | Abrí la aplicación correspondiente manualmente y comprobá que esté instalada, activada y lista para usar. Microsoft 365 web no proporciona esta integración. |
| Se informa que PowerPoint está abierto. | Guardá tus presentaciones, cerrá PowerPoint y reintentá la conversión. |
| Excel no encuentra contenido tabular en un PDF. | Comprobá si el PDF contiene texto seleccionable. Si es una imagen escaneada, aplicá OCR y revisá su calidad antes de exportar. |
| Un Excel convertido a PDF presenta texto recortado o demasiadas páginas. | Revisá los anchos de columna, el área de impresión y la escala en Excel; la exportación respeta esos ajustes. |
| La conversión termina por tiempo de espera o por un aviso de Office. | Revisá si el archivo tiene contraseña, si Office está esperando una confirmación o si una política corporativa impide abrirlo. Si persiste, registrá el mensaje exacto para reportarlo. |
| Falta el ejecutable o la carpeta `_internal/`. | Extraé nuevamente el ZIP completo. Si descargaste el código fuente, compilá el portable siguiendo la sección de desarrollo. |

## Privacidad, censura y firmas

El editor procesa los documentos localmente. Microsoft 365 se ejecuta con sus propias políticas corporativas, servicios y temporales. Abrir un enlace web utiliza el navegador y puede acceder a internet.

- **Sesión privada:** evita guardar recientes y mantiene el historial de edición en RAM. Algunas conversiones, adjuntos y operaciones de escáner necesitan temporales en disco. La aplicación intenta limpiarlos; este modo no garantiza ausencia de rastros en el equipo.
- **Copia anónima:** permite limpiar metadatos y acciones activas del PDF principal. Los archivos adjuntos se conservan y no se inspeccionan recursivamente.
- **Firmas digitales:** detecta estructuras de firma aplicada y avisa antes de reescribir el documento. No valida certificados ni cadenas de confianza; modificar un PDF firmado puede invalidar su firma.
- **Censura:** elimina contenido del resultado guardado. Conservá el original por separado y revisá la copia después de guardarla y reabrirla.

## Atajos útiles

| Atajo | Acción |
|---|---|
| `Ctrl + O` | Abrir PDF |
| `Ctrl + S` / `Ctrl + Shift + S` | Guardar / Guardar como |
| `Ctrl + P` | Imprimir |
| `Ctrl + F` | Buscar texto |
| `F3` / `Shift + F3` | Coincidencia siguiente / anterior |
| `Ctrl + Z` / `Ctrl + Y` | Deshacer / Rehacer |
| `Ctrl + 1` / `Ctrl + 2` | Ajustar al ancho / a la página |
| `Ctrl + Shift + C` | Comprimir PDF |
| `Ctrl + Shift + A` | Administrar adjuntos |
| `F4` | Mostrar u ocultar el panel lateral |
| `H` / `V` | Desplazar / Seleccionar texto |
| `T` / `R` | Insertar texto / Censurar |

## Desarrollo

Ejecutá estos comandos en PowerShell desde la raíz del repositorio.

### Preparar el entorno

```powershell
python -m venv Proyecto\.venv
.\Proyecto\.venv\Scripts\python.exe -m pip install -r Proyecto\requirements\requirements.lock
```

El archivo `requirements.lock` fija las versiones del entorno probado. `Proyecto/requirements/requirements.txt` declara las dependencias de ejecución, y `requirements-dev.txt` agrega pruebas y empaquetado con rangos de versiones.

### Abrir desde el código y ejecutar las pruebas

```powershell
.\Proyecto\run.bat
.\Proyecto\.venv\Scripts\python.exe -m pytest Proyecto\tests -q
```

La configuración de pytest mantiene su caché dentro de `Proyecto/`.

### Compilar el portable

```powershell
.\Proyecto\.venv\Scripts\python.exe Proyecto\scripts\build_portable.py
```

Se generan:

- `Programa/EditorPDFPortable/`: carpeta ejecutable completa.
- `Programa/EditorPDFPortable.zip`: paquete para entregar.
- `Proyecto/build/`: archivos intermedios de compilación.

El script resuelve el proyecto desde su ubicación y admite `--dist-dir`, `--work-dir` y `--no-zip`. Para distribuir el programa, usá el ZIP generado. Compilar o hacer commit no actualiza el ZIP publicado en GitHub Releases; la publicación es un paso separado.

### Comprobar el ejecutable compilado

```powershell
$env:PYINSTALLER_SUPPRESS_SPLASH_SCREEN = '1'
$prueba = Start-Process -FilePath '.\Programa\EditorPDFPortable\EditorPDFPortable.exe' `
    -ArgumentList '--self-test ".\Proyecto\diagnostico_runtime"' `
    -WindowStyle Hidden -Wait -PassThru
$prueba.ExitCode
Get-Content -LiteralPath '.\Proyecto\diagnostico_runtime\self_test_result.json'
```

La autoprueba usa documentos sintéticos y preferencias del editor aisladas. Requiere Word y Excel de Microsoft 365 instalados. Comprueba procesos independientes, exportación a Word y Excel, retorno de ambos formatos a PDF, imágenes, compresión cifrada y OCR. Escribe el resultado en `Proyecto/diagnostico_runtime/self_test_result.json` y devuelve código `0` cuando todas las comprobaciones pasan. No requiere escáner ni impresora.

Las ocho comprobaciones del portable no incluyen PowerPoint: esa conversión se verificó por separado desde el código fuente. El resultado detallado y el entorno probado se describen en la guía técnica.

## Validación y documentación

La integración con Microsoft 365 del **23 de octubre de 2026** se verificó con **204 pruebas automatizadas aprobadas** y **8 comprobaciones del portable aprobadas**, ambas con código de salida `0`. Además, se probaron las cinco conversiones reales: PDF a Word y Excel, y Word, Excel y PowerPoint a PDF. Se reabrieron los resultados para comprobar su contenido y se verificó que el ZIP contiene el mismo ejecutable probado.

`pip check` no detectó dependencias incompatibles. La consulta OSV de las **41 versiones** de `requirements.lock` no devolvió avisos; ese resultado no certifica ausencia de vulnerabilidades. El detalle de los motores y del alcance de las pruebas está en la [guía técnica de Microsoft 365](Proyecto/docs/MICROSOFT365.md).

- [Estructura del proyecto y ubicación de cada archivo](Proyecto/docs/ESTRUCTURA.md).
- [Registro técnico de correcciones y alcance de seguridad](Proyecto/docs/auditoria/CORRECCIONES_AUDITORIA.md).
- [Reportar un problema](https://github.com/Fede1771/Editor-portable/issues): indicá los pasos para reproducirlo, el mensaje de error y si ocurre en el portable o al ejecutar desde Python.

Los ejecutables, entornos Python, cachés, archivos de compilación e informes locales de auditoría están excluidos del repositorio.
