# Organización del proyecto

La carpeta principal presenta dos carpetas y dos archivos de uso habitual:

```text
Editor portable/
├── Abrir_EditorPortable.bat       Doble clic para abrir el editor
├── README.md                     Información general
├── Programa/                     Programa listo para usar o entregar
│   ├── EditorPDFPortable.zip
│   └── EditorPDFPortable/
│       ├── EditorPDFPortable.exe
│       ├── Abrir_EditorPortable.bat
│       └── _internal/            Bibliotecas y recursos del portable
└── Proyecto/                     Desarrollo y documentación
    ├── main.py                   Punto de entrada de Python
    ├── run.bat                   Abre el editor desde el código
    ├── app/                      Módulos de la aplicación
    ├── data/                     Iconos, splash e idiomas OCR
    ├── requirements/             Dependencias de ejecución y desarrollo
    ├── scripts/                  Compilador y configuración de PyInstaller
    ├── tests/                    Pruebas automatizadas
    │   └── fixtures/             PDFs de prueba
    ├── pytest.ini                Mantiene la caché dentro de Proyecto
    ├── docs/                     Documentación
    │   └── auditoria/
    │       ├── CORRECCIONES_AUDITORIA.md
    │       └── local/            Informes y evidencias históricos locales
    ├── build/                    Intermedios de compilación
    ├── .venv/                    Entorno de Python
    └── .pytest_cache/            Caché de pruebas
```

Los archivos técnicos de Git permanecen en la raíz. `.gitignore` y el enlace de compatibilidad `.venv` tienen el atributo oculto de Windows; `.git` ya estaba oculto. No se modificó la opción global del Explorador para mostrar archivos ocultos.

El entorno real está en `Proyecto/.venv/`. El enlace local `.venv` de la raíz permite que los lanzadores de pip y otros comandos instalados antes del traslado sigan resolviendo su ruta original. No contiene otra copia del entorno. Al clonar el repositorio se crea un entorno nuevo; no es necesario copiar ese enlace.

## Usar y entregar el programa

Hacé doble clic en `Abrir_EditorPortable.bat` desde la carpeta principal. Para entregar el programa usá `Programa/EditorPDFPortable.zip`.

Al utilizar la carpeta descomprimida, conservá completo su contenido, incluido `_internal/`.

## Desarrollar desde la raíz del repositorio

Preparar un entorno nuevo con las versiones probadas:

```powershell
python -m venv Proyecto\.venv
.\Proyecto\.venv\Scripts\python.exe -m pip install -r Proyecto\requirements\requirements.lock
```

Para instalar las dependencias de desarrollo mediante rangos de versiones:

```powershell
.\Proyecto\.venv\Scripts\python.exe -m pip install -r Proyecto\requirements\requirements-dev.txt
```

Abrir desde el código, ejecutar las pruebas y compilar:

```powershell
.\Proyecto\run.bat
.\Proyecto\.venv\Scripts\python.exe -m pytest Proyecto\tests -q
.\Proyecto\.venv\Scripts\python.exe Proyecto\scripts\build_portable.py
```

También se puede trabajar desde `Proyecto/`, usando las rutas internas sin ese prefijo. El compilador resuelve las rutas desde el script y genera el ejecutable y ZIP en `Programa/`, y los intermedios en `Proyecto/build/`, aunque se invoque desde otra carpeta. Admite `--dist-dir`, `--work-dir` y `--no-zip`.

`Programa/`, los entornos Python, los intermedios y cachés, y los informes locales están excluidos de Git.

## Dónde guardar archivos nuevos

- Código: `Proyecto/app/`.
- Recursos del programa: `Proyecto/data/`; incluirlos en el `.spec` cuando corresponda.
- Herramientas de desarrollo: `Proyecto/scripts/`.
- Pruebas y muestras: `Proyecto/tests/` y `Proyecto/tests/fixtures/`.
- Documentación compartida: `Proyecto/docs/`.
- Informes y evidencia locales: `Proyecto/docs/auditoria/local/`.
- Ejecutables y ZIP generados: `Programa/`; intermedios: `Proyecto/build/`.

## Correspondencia con las rutas anteriores

| Ubicación anterior | Ubicación actual |
|---|---|
| `app/`, `data/`, `main.py` y `run.bat` en la raíz | Dentro de `Proyecto/` |
| `build_portable.py` en la raíz | `Proyecto/scripts/build_portable.py` |
| `EditorPDFPortable.spec` en la raíz | `Proyecto/scripts/EditorPDFPortable.spec` |
| Los tres archivos `requirements*` de la raíz | `Proyecto/requirements/` |
| `tests/muestra.pdf` | `Proyecto/tests/fixtures/muestra.pdf` |
| `docs/CORRECCIONES_AUDITORIA.md` | `Proyecto/docs/auditoria/CORRECCIONES_AUDITORIA.md` |
| `informes_auditoria/` | `Proyecto/docs/auditoria/local/` |
| `Informes_para_Antigravity.md` en la raíz | Se conserva la copia idéntica en `Proyecto/docs/auditoria/local/` |
| `dist/` | `Programa/` |
| `build/` y `.pytest_cache/` en la raíz | Dentro de `Proyecto/` |
| `.venv/` en la raíz | `Proyecto/.venv/`, con enlace de compatibilidad oculto en la ruta anterior |

Los informes históricos conservan su contenido original; sus referencias a rutas anteriores deben interpretarse con esta tabla.

## Comprobación del traslado

El 23/10/2026 se aprobaron las 193 pruebas con salida 0 desde la nueva ubicación. La compilación desde otra carpeta generó el programa y el ZIP en `Programa/`. Se probó el acceso de la raíz con la autoprueba del portable: procesos independientes, Word, Excel, imágenes, compresión cifrada y OCR. El ZIP conserva el mismo EXE y acceso verificados. También se comprobó que las pruebas mantienen su caché dentro de `Proyecto/`.
