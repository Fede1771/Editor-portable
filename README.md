# 📄 Editor PDF Portable

[![Windows](https://img.shields.io/badge/Plataforma-Windows%20x64-0078D6?logo=windows&logoColor=white)](https://github.com/Fede1771/Editor-portable/releases)
[![Procesamiento local](https://img.shields.io/badge/Procesamiento-100%25%20Local-success)](#-seguridad-y-privacidad)
[![Privacidad](https://img.shields.io/badge/Privacidad-Cero%20Huella-blue)](#-seguridad-y-privacidad)
[![Sin Instalación](https://img.shields.io/badge/Portable-Sin%20instalación-informational)](#-cómo-empezar)

> **Leé, editá, organizá, censurá y creá documentos PDF desde una única aplicación portable para Windows.**
>
> Diseñado para trabajar de forma ágil, privada y sin conexión con pólizas, legajos, formularios, contratos y documentación corporativa.

---

## ⬇️ Descargar para Windows

[![Descargar ZIP para Windows](https://img.shields.io/badge/DESCARGAR_ZIP-Para_Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Fede1771/Editor-portable/releases/latest/download/EditorPDFPortable.zip)

[📦 Ver todas las versiones publicadas](https://github.com/Fede1771/Editor-portable/releases)

---

## 🚀 Funcionalidades principales

### 📑 Edición y lectura
- **Edición directa de texto:** Modificá bloques de texto existentes respetando tipografía, tamaño y alineación original, o insertá nuevos cuadros de texto.
- **Visualización flexible:** Navegación en pestañas múltiples, modo continuo, una página o dos páginas, zoom fluido y rotación de vista.
- **Búsqueda interactiva:** Buscador integrado con resaltado de coincidencias y navegación rápida.

### ✂️ Organización de páginas
- **Manipulación completa:** Combiná varios documentos, dividí PDFs, reordená páginas con arrastrar y soltar, rotá, duplicá o eliminá.
- **Herramientas de página:** Insertá páginas en blanco o extraé páginas a un archivo nuevo.
- **Diseño y estructura:** Agregá numeración de página, encabezados, pies y marcas de agua personalizadas.

### ✍️ Anotaciones y formularios
- **Herramientas de marcado:** Resaltado de texto, subrayado, tachado y dibujo libre a mano alzada.
- **Notas adhesivas:** Añadí comentarios y observaciones emergentes en cualquier parte del documento.
- **AcroForms:** Completá formularios interactivos (campos de texto, casillas de verificación, opciones) y **aplaná formularios** para fijar permanentemente los datos completados.

### 🔍 OCR y Reconocimiento de texto
- **OCR local integrado:** Procesá documentos escaneados e imágenes mediante Tesseract (español e inglés) para transformarlos en PDFs con texto seleccionable, copiable y buscable.
- **100% offline:** El reconocimiento óptico se ejecuta íntegramente en tu procesador, sin enviar documentos a la nube ni consumir datos.

### 🗜️ Optimización y compresión
- **Compresión inteligente:** Perfiles específicos según el destino (envío por correo electrónico, archivo digital de bajo peso o legajos de alta resolución).
- **Control de resolución:** Ajuste automático de DPI y compresión de imágenes incrustadas manteniendo la legibilidad.

### 🛡️ Censura y privacidad (Cero Huella)
- **Censura destructiva:** Ocultá datos confidenciales (DNI, nombres, datos bancarios) por selección manual de área o mediante búsqueda automática de patrones. El contenido original se purga definitivamente del archivo.
- **Modo Sesión Privada:** No registra documentos recientes ni persiste rutas en el registro del sistema; limpia temporales al cerrar.
- **Limpieza de metadatos:** Eliminá autores, títulos, software creador e historiales del archivo PDF para compartir copias anónimas y seguras.
- **Protección de firmas digitales:** Detección de firmas existentes y advertencia previa antes de modificar el documento para evitar invalidar firmas válidas por accidente.

### 📥 Creación y exportación a imágenes
- **Crear PDF desde archivos (`Ctrl + N`):** Generá documentos PDF nuevos a partir de imágenes (`.png`, `.jpg`, `.bmp`, `.tiff`) o documentos de Office (`.docx`, `.xlsx`, `.pptx` requiriendo Microsoft 365 local instalado).
- **Exportar a imágenes:** Guardá las páginas del documento como imágenes independientes de alta definición (PNG o JPEG) con selección personalizada de páginas y resolución (DPI).
- **Gestión de adjuntos:** Consultá, extraé, incrustá o eliminá archivos adjuntos embebidos dentro del PDF.

---

## 🔒 Seguridad y privacidad

- **Procesamiento estrictamente local:** Todos los archivos permanecen en tu computadora. El editor no incluye telemetría, no recolecta analíticas ni envía datos a servidores externos.
- **Censura real:** Al censurar texto o imágenes, los datos subyacentes se borran físicamente del PDF, impidiendo su recuperación mediante copia de texto o extracción de capas.
- **Cero dependencias externas:** No requiere Java, LibreOffice ni Python preinstalado. Todo viene empaquetado en el directorio del programa.

---

## ⚡ Cómo empezar

1. **Descargá el archivo ZIP** usando el botón superior o desde la sección de [Releases](https://github.com/Fede1771/Editor-portable/releases).
2. **Extraé el contenido** en cualquier carpeta de tu disco local o pendrive (asegurate de conservar la subcarpeta `_internal/`).
3. **Ejecutá `EditorPDFPortable.exe`** o hacé doble clic en `Abrir_EditorPortable.bat`.
4. Arrastrá cualquier archivo PDF a la ventana o presioná `Ctrl + O` para abrirlo.

---

## ⌨️ Atajos de teclado más utilizados

| Atajo | Acción |
|---|---|
| `Ctrl + O` | Abrir documento PDF |
| `Ctrl + S` | Guardar cambios |
| `Ctrl + Shift + S` | Guardar como copia nueva |
| `Ctrl + N` | Crear PDF desde archivos (imágenes u Office) |
| `Ctrl + W` | Cerrar pestaña actual |
| `Ctrl + F` | Buscar texto en el documento |
| `Ctrl + P` | Imprimir documento |
| `Ctrl + Z` / `Ctrl + Y` | Deshacer / Rehacer acción |
| `Ctrl + +` / `Ctrl + -` | Aumentar / Reducir zoom |
| `Ctrl + Shift + C` | Comprimir y optimizar PDF |
| `Ctrl + Shift + A` | Administrador de archivos adjuntos |

---

## 💻 Requisitos del sistema

- **Sistema Operativo:** Windows 10 o Windows 11 (64 bits).
- **Permisos:** No requiere permisos de administrador ni instalación en el sistema.
- **Microsoft 365 de escritorio (opcional):** Únicamente necesario si deseás crear PDFs a partir de archivos de Word, Excel o PowerPoint mediante `Ctrl + N`. Todas las demás funciones (lectura, edición, anotaciones, OCR, formularios, compresión y exportación a imágenes) funcionan de forma autónoma.

---

[📘 Documentación de Microsoft 365](Proyecto/docs/MICROSOFT365.md) · [🛡️ Registro técnico de seguridad y auditoría](Proyecto/docs/auditoria/CORRECCIONES_AUDITORIA.md) · [🐛 Reportar un problema o sugerencia](https://github.com/Fede1771/Editor-portable/issues)
