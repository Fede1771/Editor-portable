# Editor PDF Portable

**Editor de PDF para Windows de 64 bits, con procesamiento local y OCR en español e inglés.**

Permite leer, editar, organizar, censurar y convertir documentos desde una interfaz con pestañas. La versión portable funciona sin instalar Python y se puede llevar en una carpeta o pendrive.

**[Descargar el ZIP de la última versión publicada](https://github.com/Fede1771/Editor-portable/releases/latest/download/EditorPDFPortable.zip)** · [Ver versiones publicadas](https://github.com/Fede1771/Editor-portable/releases)

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
| Exportar PDF a Word o Excel | Las bibliotecas necesarias están incluidas en el portable. |
| Crear PDF desde Word, Excel o PowerPoint | LibreOffice instalado y disponible para la aplicación. |
| Crear PDF desde un escáner | Escáner y controlador compatibles con WIA en Windows. |
| Trabajar con el código | Entorno probado: Windows x64 y CPython 3.14. |

## Privacidad, censura y firmas

Los documentos se procesan localmente. Abrir un enlace web desde la aplicación utiliza el navegador y puede acceder a internet.

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

El script resuelve el proyecto desde su ubicación y admite `--dist-dir`, `--work-dir` y `--no-zip`. Para distribuir el programa, usá el ZIP generado.

### Comprobar el ejecutable compilado

```powershell
$env:PYINSTALLER_SUPPRESS_SPLASH_SCREEN = '1'
.\Programa\EditorPDFPortable\EditorPDFPortable.exe --self-test .\Proyecto\diagnostico_runtime
```

La autoprueba usa documentos sintéticos y preferencias aisladas. Comprueba procesos independientes, exportación a Word y Excel, imágenes, compresión cifrada y OCR. Escribe el resultado en `Proyecto/diagnostico_runtime/self_test_result.json` y devuelve código `0` cuando todas las comprobaciones pasan. No requiere Microsoft Office, escáner ni impresora.

## Validación y documentación

La reorganización del **23 de octubre de 2026** se verificó con **193 pruebas automatizadas aprobadas** y **6 comprobaciones del portable aprobadas**, ambas con código de salida `0`. También se comprobó el acceso de la carpeta principal y que el ZIP contiene el mismo ejecutable probado.

- [Estructura del proyecto y ubicación de cada archivo](Proyecto/docs/ESTRUCTURA.md).
- [Registro técnico de correcciones y alcance de seguridad](Proyecto/docs/auditoria/CORRECCIONES_AUDITORIA.md).
- [Reportar un problema](https://github.com/Fede1771/Editor-portable/issues): indicá los pasos para reproducirlo, el mensaje de error y si ocurre en el portable o al ejecutar desde Python.

Los ejecutables, entornos Python, cachés, archivos de compilación e informes locales de auditoría están excluidos del repositorio.
