# 📄 Editor PDF Portable

[![Windows](https://img.shields.io/badge/Plataforma-Windows%20x64-0078D6?logo=windows&logoColor=white)](https://github.com/Fede1771/Editor-portable/releases)
[![Procesamiento local](https://img.shields.io/badge/Procesamiento-Local-success)](#-seguridad-y-privacidad)
[![Microsoft 365](https://img.shields.io/badge/Office-Microsoft%20365-orange)](#-qué-necesitás)

> **Leé, editá, organizá y convertí documentos PDF desde una misma aplicación.**
>
> Incluye OCR en español e inglés, censura de información y herramientas para trabajar con pólizas, legajos, formularios y documentación de la compañía.

---

## ⬇️ Descargar para Windows

[![Descargar ZIP para Windows](https://img.shields.io/badge/DESCARGAR_ZIP-Para_Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Fede1771/Editor-portable/releases/latest/download/EditorPDFPortable.zip)

[Ver versiones publicadas](https://github.com/Fede1771/Editor-portable/releases)

---

## 🚀 Qué podés hacer

- **Leer y editar:** abrí varios PDFs en pestañas, buscá texto, modificá bloques de texto y agregá imágenes, enlaces o comentarios.
- **Organizar páginas:** combiná, dividí, reordená, rotá, recortá, extraé o eliminá páginas. Agregá numeración y marcas de agua.
- **Reducir el peso:** usá perfiles de compresión para correo, archivo corporativo o legajos con mayor detalle de imágenes. El tamaño final depende del contenido.
- **Reconocer escaneos:** aplicá OCR local en español e inglés para obtener texto buscable y copiable.
- **Convertir documentos:** exportá PDF a Word o Excel y creá PDFs desde Word, Excel o PowerPoint con Microsoft 365. También exportá imágenes, texto y HTML.
- **Completar formularios:** editá campos, casillas y listas de formularios AcroForm, y aplanalos cuando necesites fijar sus valores.
- **Gestionar adjuntos:** consultá, agregá, extraé o eliminá los archivos incluidos dentro de un PDF.

---

## 🔒 Seguridad y privacidad

- **Procesamiento local:** el editor procesa los documentos en el equipo. Las conversiones Office utilizan las aplicaciones instaladas de Microsoft 365, sujetas a las políticas y servicios de la compañía. Abrir enlaces web puede acceder a internet.
- **Sesión privada:** evita guardar documentos recientes y mantiene el historial de edición en RAM. Algunas operaciones necesitan temporales en disco; se intenta limpiarlos al finalizar, sin garantizar ausencia de rastros.
- **Censura de información:** elimina contenido mediante un rectángulo o una búsqueda de texto. Conservá el original y revisá la copia guardada antes de compartirla.
- **Limpieza de metadatos:** la copia anónima permite limpiar metadatos y acciones activas del PDF principal. Los adjuntos se conservan y no se inspeccionan recursivamente.
- **Protección de firmas:** detecta estructuras de firma aplicada y avisa antes de reescribir el documento. No valida certificados; modificar un PDF firmado puede invalidar su firma.
- **Conversiones protegidas:** los archivos Office de origen se abren como sólo lectura. La salida se valida antes de reemplazar el destino y, si la conversión falla, se conserva el archivo anterior.
- **Datos literales en Excel:** al exportar un PDF, el XLSX guarda texto sin fórmulas ni conexiones al PDF temporal, evitando que el contenido extraído se evalúe como una fórmula.

---

## ⚡ Cómo empezar

1. **Descargá el ZIP** con el botón de arriba.
2. Elegí **Extraer todo…** y conservá completa la carpeta extraída, incluida **`_internal/`**.
3. Abrí **`EditorPDFPortable.exe`** o **`Abrir_EditorPortable.bat`**. Arrastrá un PDF a la ventana o usá `Ctrl + O`.

Para convertir un PDF a Word o Excel, elegí **Exportar / Convertir a…**. Para crear un PDF desde archivos Office, usá **Crear PDF desde archivos…** (`Ctrl + N`) y guardá el resultado con `Ctrl + S`.

### 💻 Qué necesitás

- **Windows de 64 bits.** El portable incluye sus bibliotecas; no requiere instalar Python.
- **Microsoft 365 de escritorio instalado y activado** para las conversiones Office: Word para DOCX, Excel con Power Query PDF para XLSX y la aplicación correspondiente para convertir Office a PDF. La versión web no reemplaza estos requisitos.
- La lectura, edición y el OCR de PDF funcionan sin Microsoft 365. Para convertir una presentación, guardá tus cambios y cerrá PowerPoint antes de comenzar.

Revisá el contenido y el diseño después de editar o convertir un documento, especialmente si contiene escaneos, tablas o firmas.

---

[📘 Detalles de Microsoft 365](Proyecto/docs/MICROSOFT365.md) · [🛡️ Registro técnico de seguridad](Proyecto/docs/auditoria/CORRECCIONES_AUDITORIA.md) · [🐛 Reportar un problema](https://github.com/Fede1771/Editor-portable/issues)
