# Editor PDF Portable

Una suite completa, ligera y autónoma para la visualización, edición in situ, organización, creación, reconocimiento de texto (OCR), conversión y optimización de documentos PDF en Windows.

Diseñado para ser **100% portable**: puede ejecutarse en cualquier PC con Windows sin necesidad de instalar Python, librerías adicionales ni software de terceros.

---

## Modos de Ejecución

### 1. Acceso Directo de Escritorio
Si utilizas el acceso directo creado en tu Escritorio de Windows:
- **Doble clic en:** `Editor PDF Portable` (con su icono oficial rojo).

### 2. Modo Portable (Para llevar en un Pendrive o a otra PC)
No requiere tener Python instalado ni permisos de administrador:
- **Doble clic en:** `Abrir_EditorPortable.bat` (en la raíz de la carpeta), o
- **Ejecutable directo:** `dist\EditorPDFPortable\EditorPDFPortable.exe`

> **Para compartir o usar en otra computadora:**  
> Basta con copiar la carpeta completa `dist\EditorPDFPortable` (o comprimirla en un archivo `.zip`) a cualquier memoria USB o disco externo. Funciona de inmediato en cualquier PC con Windows 10 u 11.

### 3. Modo Desarrollo (Código Fuente)
Para desarrolladores o usuarios que deseen modificar el código fuente con el entorno virtual:
- **Doble clic en:** `run.bat`
- O desde la consola de comandos de PowerShell:
  ```powershell
  .\.venv\Scripts\python.exe main.py [archivo.pdf]
  ```

---

## Resumen de Funcionalidades

### 1. Visor Avanzado
- **Modos de visualización:** Página simple, desplazamiento vertical continuo y vista de dos páginas (estilo libro).
- **Zoom fluido:** De 25% hasta 500%, botones de ajuste automático al ancho de página (`Ctrl+1`) y a página completa (`Ctrl+2`).
- **Panel lateral compacto:**
  - **Miniaturas (`📄`):** navegación visual rápida, selección múltiple y reordenamiento arrastrando.
  - **Marcadores / Índice (`📑`):** navegación jerárquica por secciones y títulos del PDF.
  - **Comentarios embebidos (`💬`):** árbol con todas las notas y resaltados existentes en el PDF con contador dinámico.
  - **Archivos adjuntos embebidos (`📎`):** pestaña que detecta y lista todos los archivos incrustados en el PDF con sus iconos oficiales de Windows, peso y fecha.
- **Impresión nativa directa (`Ctrl+P`):** Cuadro de diálogo oficial de Windows para imprimir a cualquier impresora física o virtual con selección de rango de páginas.
- **Pastilla flotante de acciones rápidas:** Al seleccionar cualquier fragmento de texto con la herramienta de selección (`V`), se despliega una mini-burbuja flotante con acceso instantáneo a `[ Copiar ]`, `[ 🖍 Resaltar ]` y `[ ̶S̶ Tachar ]`.
- **Plegado inteligente del panel lateral:** En documentos breves (1 o 2 páginas) sin marcadores ni adjuntos, el panel lateral inicia plegado automáticamente para una visualización a pantalla completa.
- **Navegación ultra rápida con teclado:** Desplazamiento fluido con `Espacio` (avanzar) y `Shift+Espacio` (retroceder), flechas `←` / `→` o `RePág` / `AvPág`.
- **Búsqueda flotante inteligente (`Ctrl+F`):** Barra flotante moderna estilo navegador/Acrobat en la esquina superior derecha que se despliega con `Ctrl+F` o botón lupa, cuenta coincidencias en tiempo real y se oculta con `Esc`.
- **Pantalla de bienvenida y Documentos recientes:** Área inicial limpia con acceso directo a archivos abiertos recientemente (`Archivo -> Abrir recientes`), creación en blanco o arrastrar y soltar directo.
- **Múltiples pestañas:** Apertura simultánea de varios documentos con navegación por pestañas independientes.
- **Protección por contraseña:** Apertura y autenticación de documentos PDF protegidos.

### 2. Organizar y Gestionar Páginas
- **Insertar:** Añade páginas en blanco o páginas provenientes de otros archivos PDF en cualquier posición.
- **Extraer:** Guarda páginas seleccionadas en un nuevo archivo PDF independiente.
- **Eliminar y Duplicar:** Borra páginas seleccionadas (`Supr`) o duplícalas al instante.
- **Rotación:** Gira páginas seleccionadas 90° en sentido horario, antihorario o 180°.
- **Reordenar:** Arrastra miniaturas en el panel lateral o usa los atajos `Alt + Flecha Arriba / Abajo`.
- **Dividir PDF:** 
  - Dividir cada *N* páginas.
  - Dividir por rangos personalizados (ej. `1-3, 5, 8-10`).
  - Dividir automáticamente por marcadores de nivel superior.
- **Recortar márgenes:** Ajuste visual y milimétrico de márgenes en páginas seleccionadas o en todo el documento.
- **Marcas de agua:** Texto personalizado con ángulo, tamaño, color y nivel de opacidad/transparencia.
- **Encabezados y Pies de página:** Plantillas configurables con sustitución dinámica de `{n}` (número de página), `{total}` (total de páginas) y `{bates}` (numeración Bates correlativa con ceros a la izquierda).
- **Color de fondo:** Aplicación de fondos de color personalizados a páginas seleccionadas.

### 3. Crear PDF desde Múltiples Fuentes
- **Combinar archivos:** Agrupa múltiples PDFs, imágenes y documentos en un único PDF con marcadores automáticos por archivo de origen.
- **Conversión de Office:** Importa y convierte archivos de Microsoft Office (`.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, etc.) utilizando LibreOffice en segundo plano sin intervención manual.
- **Desde imágenes:** Convierte colecciones de imágenes (PNG, JPG, TIFF, BMP) ajustándolas a página completa o tamaño original.
- **Desde texto o HTML:** Renderiza archivos de texto plano o páginas web HTML directamente a formato PDF.
- **Desde el portapapeles:** Pega cualquier captura o imagen del portapapeles como una nueva página de PDF.
- **Desde escáner:** Compatible con escáneres compatibles con Windows WIA para digitalizar páginas por lotes.

### 4. Edición de Contenido In Situ (In-Place Editing)
- **Detección automática de tipografía, tamaño, color y estilo:** Al hacer clic sobre cualquier texto (sea un PDF digital nativo o un PDF escaneado procesado con OCR), el sistema inspecciona automáticamente:
  - **Tamaño de letra (`pt`):** Detección exacta en PDFs digitales y calibración por altura visual de renglón en PDFs con OCR.
  - **Color del texto:** Lee los metadatos de color del vector o analiza por muestreo espectral de píxeles el tono real de la tinta (negro, azul, gris, rojo, etc.).
  - **Familia tipográfica y estilo:** Clasifica la fuente (Sans-Serif / Helvetica, Serif / Times Roman o Monoespaciada / Courier) e identifica automáticamente si el texto está en **Negrita** (*Bold*) o **Cursiva** (*Italic*).
  - **Alineación:** Reconoce si el bloque está alineado a la izquierda, centrado o a la derecha.
  - **Color de fondo del recuadro:** Detecta el color de la tarjeta o fondo (blanco, gris claro, crema) para reemplazar el texto de forma 100% limpia sin dejar recuadros visibles.
- **Aislamiento inteligente de recuadros y celdas:** Al hacer clic sobre cualquier palabra o título (incluso en diagramas complejos de correlatividades, tarjetas de asignaturas o tablas de múltiples columnas), el algoritmo aísla únicamente la celda o recuadro clickeado sin invadir las columnas ni renglones adyacentes.
- **Ajuste automático de tipografía (*Auto-fit*):** Incorpora un cálculo dinámico de altura de línea y un algoritmo de ajuste inteligente. Si el texto editado es más extenso o proviene de un escaneo con resolución alta, el editor reduce proporcionalmente el tamaño de la fuente para que encaje perfectamente dentro del recuadro original, evitando desbordes o pisar elementos inferiores. Incluye casilla configurable en el diálogo de edición (*"Ajustar automáticamente al recuadro"*).
- **Selección por arrastre:** Con la herramienta de texto activa (`T`), también puedes arrastrar un recuadro con el ratón sobre cualquier sección para editar estrictamente lo que quede encerrado dentro.
- **Preservación total de recuadros, tablas y contornos:** Detecta automáticamente el contorno de tarjetas, casillas y celdas (tanto en trazados vectoriales como en documentos escaneados o procesados con OCR). La redacción se efectúa de forma quirúrgica en el interior sin tocar ni borrar los bordes originales, y el recuadro se refuerza para garantizar máxima nitidez y que nunca se pierda el formato del diagrama.
- **Edición limpia sin marcos negros:** Al modificar el texto, el editor limpia el fondo original con blanco puro (redacción de píxeles) e inserta la tipografía actualizada con ajuste automático de ancho.
- **Cuadros de texto libres:** Inserta párrafos o notas nuevas en cualquier coordenada eligiendo tipografía, tamaño y color.
- **Censura permanente (*Redact*):** 
  - Herramienta manual de área (`R`) para tapar información confidencial con relleno negro. A diferencia de un simple dibujo, destruye físicamente el texto e imágenes vectoriales subyacentes.
  - Búsqueda y censura automática: busca palabras o patrones en todo el PDF y las censura en un solo paso.
- **Insertar imágenes:** Inserta logotipos o imágenes (`I`) con previsualización y posicionamiento interactivo.
- **Hipervínculos:** Inserta enlaces web cliqueables (`L`) sobre cualquier región rectangular.
- **Extracción de imágenes:** Exporta todas las imágenes incrustadas dentro del PDF a una carpeta local.
- **Deshacer / Rehacer:** Pila de historial completa (`Ctrl+Z` / `Ctrl+Y`) en todas las operaciones.

---

### Guía Rápida: Cómo Editar un PDF Escaneado o Gráfico

Si abres un PDF que es un escaneo o una imagen y al principio no puedes seleccionar ni editar las palabras:
1. **Aplicar OCR:** Ve al menú superior **Herramientas -> Reconocimiento de texto (OCR)...** (o presiona el botón OCR en la barra de herramientas).
2. **Configuración predeterminada óptima:** Por defecto ya viene configurado en **Español** y con la resolución más alta (**Máxima precisión y nitidez a 300 DPI**, ideal para esquemas técnicos, tablas y letras pequeñas).
3. **Procesar:** Haz clic en Aceptar. El sistema creará una capa vectorial transparente de texto legible en segundo plano.
4. **Editar:** Presiona la tecla `T` (o el icono de texto en la barra) y haz un clic directo sobre la palabra o recuadro que deseas cambiar. Se abrirá el editor con el texto detectado, listo para modificar y con auto-ajuste para no desbordar el recuadro.

### 5. Anotaciones de Estudio y Dibujo Libre
- **Lápiz / Trazo libre (`P`):** Dibuja trazos, anotaciones manuscritas, flechas o esquemas directamente sobre la hoja con renderizado vectorial en tiempo real.
- **Anotaciones de estudio:**
  - **Resaltador fluorescente (`Shift+H`):** Marca párrafos e ideas clave en amarillo brillante.
  - **Subrayado (`Shift+U`):** Subraya frases o líneas en azul.
  - **Tachado (`Shift+K`):** Tacha fragmentos en rojo para revisiones o correcciones.
  - **Notas adhesivas / Comentarios (`N`):** Haz clic en cualquier lugar del documento para dejar un comentario con autor y fecha.
- **Visualizador de comentarios embebidos:**
  - **Pestaña lateral «Comentarios»:** Lista de forma agrupada por página todas las notas, comentarios y anotaciones preexistentes del PDF. Al hacer clic en un comentario, el visor salta y se posiciona directamente sobre él.
  - **Inspección rápida al pasar el ratón (Tooltips):** Pasa el cursor sobre cualquier nota, comentario o resaltado embebido para ver instantáneamente su autor y texto en una ventana flotante.

### 6. Formularios Interactivos (AcroForms)
- **Completar campos de formulario:** Diálogo inteligente que lista todos los campos de texto, casillas de verificación (*checkboxes*) y desplegables del documento, permitiendo rellenarlos de manera rápida y ordenada.
- **Aplanar formulario (*Flatten*):** Convierte todos los campos editables en texto y gráficos fijos integrados en el PDF, impidiendo que sean alterados posteriormente por terceros.

### 7. Reconocimiento Óptico de Caracteres (OCR)
- **Motor Tesseract integrado:** No requiere instalar binarios de Tesseract ni variables de entorno.
- **Modelos multilingües incluidos:** Soporta español (`spa`) e inglés (`eng`) empaquetados localmente, con **Español predeterminado**.
- **Capa de texto invisible:** Convierte PDFs escaneados o basados en imágenes en documentos con texto seleccionable, copiable y con búsqueda indexada.
- **Máxima precisión por defecto:** Preconfigurado por omisión a la calidad más alta (**300 DPI**), garantizando detección óptima en letras pequeñas, cajas, números y diagramas.

### 8. Exportar y Convertir
- **A Microsoft Word (.docx):** Convierte el PDF a documento de Word editable conservando párrafos, columnas y formato.
- **A Microsoft Excel (.xlsx):** Detecta tablas y estructuras tabulares y las exporta a hojas de cálculo organizadas.
- **A Imágenes de alta resolución:** Exporta páginas completas a PNG o JPG con resolución configurable (72 a 300 DPI).
- **A Texto (.txt) y HTML:** Extrae el contenido en formato texto plano estructurado o página web navegable.

### 9. Optimización y Reducción de Tamaño
- **Recompresión de imágenes:** Reduce imágenes internas convirtiéndolas a JPEG con nivel de calidad (0-100%) y resolución máxima límite (DPI).
- **Limpieza de metadatos:** Elimina metadatos ocultos (autor, fechas, software generador) para máxima privacidad.
- **Garbage collection & Deflate:** Elimina flujos no referenciados, fuentes huérfanas y compacta las tablas internas de objetos.

---

## Estructura del Proyecto

```
Editor portable/
├── .venv/                      # Entorno virtual de desarrollo Python
├── app/                        # Módulos del núcleo de la aplicación
│   ├── __init__.py             # Inicializador del paquete
│   ├── annotations.py          # Gestión de comentarios, resaltados, notas y trazos de tinta
│   ├── background.py           # Tareas asíncronas en segundo plano (QThread)
│   ├── content_ops.py          # Edición in situ, censura, texto, imágenes y enlaces
│   ├── conversion.py           # Conversores a Word (.docx), Excel (.xlsx), HTML, TXT, imágenes
│   ├── creation.py             # Motor de creación de PDFs (Office, imágenes, escáner, web)
│   ├── dialogs.py              # Formularios y ventanas modales
│   ├── doc_tab.py              # Controlador de pestaña, árbol de comentarios y pila Undo/Redo
│   ├── forms.py                # Gestión, inspección y aplanado de AcroForms
│   ├── main_window.py          # Ventana principal, menús, barras de herramientas y atajos
│   ├── ocr.py                  # Integración del motor de OCR Tesseract de PyMuPDF
│   ├── operations.py           # Manipulación de páginas (rotar, dividir, bates, marcas)
│   ├── optimizer.py            # Motor de compresión y reducción de tamaño
│   ├── search_bar.py           # Barra de búsqueda flotante interactiva estilo navegador
│   ├── selection_popup.py      # Mini-burbuja flotante de acciones rápidas sobre texto
│   ├── viewer.py               # Canvas gráfico, zoom, navegación y eventos del mouse
│   └── welcome.py              # Pantalla de bienvenida minimalista y documentos recientes
├── data/                       # Recursos estáticos de la aplicación
│   ├── tessdata/               # Modelos entrenados de OCR (spa.traineddata, eng.traineddata)
│   ├── app_icon.ico            # Icono oficial para el ejecutable y accesos directos
│   └── app_icon.png            # Icono en alta resolución para la ventana y barra de tareas
├── dist/                       # Distribución portable empaquetada
│   └── EditorPDFPortable/      # CARPETA PORTABLE (la que se copia a un pendrive)
│       ├── _internal/          # Binarios congelados y librerías C++
│       └── EditorPDFPortable.exe
├── tests/                      # Suite de pruebas automatizadas y muestras
│   ├── muestra.pdf             # PDF de muestra para pruebas
│   └── test_suite.py           # Suite automatizada integral (8 fases)
├── .gitignore                  # Reglas de exclusión de archivos temporales
├── Abrir_EditorPortable.bat    # Lanzador de la versión portable compilada
├── build_portable.py           # Script para volver a compilar el portable con PyInstaller
├── EditorPDFPortable.spec      # Configuración de compilación PyInstaller
├── main.py                     # Punto de entrada para ejecución desde código fuente
├── README.md                   # Documentación y manual de usuario
├── requirements.txt            # Dependencias del proyecto
└── run.bat                     # Lanzador del entorno de desarrollo
```

---

## Atajos de Teclado Principales

| Atajo | Acción |
| :--- | :--- |
| `Ctrl + O` | Abrir documento PDF |
| `Ctrl + S` | Guardar cambios |
| `Ctrl + Shift + S` | Guardar como... |
| `Ctrl + W` | Cerrar pestaña activa |
| `Ctrl + N` | Crear nuevo PDF |
| `Ctrl + Shift + N` | Combinar archivos en un PDF |
| `Ctrl + Z` | Deshacer última acción |
| `Ctrl + Y` | Rehacer última acción |
| `Ctrl + F` | Abrir buscador de texto |
| `F3` / `Shift + F3` | Coincidencia siguiente / anterior |
| `F4` | Mostrar / ocultar panel lateral |
| `Ctrl + Shift + A` | Ver y gestionar archivos adjuntos embebidos |
| `Ctrl + +` / `Ctrl + -` | Aumentar / reducir zoom |
| `Ctrl + Rueda Ratón` | Zoom interactivo centrado en cursor |
| `Ctrl + 1` | Ajustar vista al ancho de página |
| `Ctrl + 2` | Ajustar vista a página completa |
| `H` | Herramienta Mano (desplazamiento) |
| `V` | Herramienta Seleccionar y copiar texto |
| `T` | Herramienta Texto (editar in situ o insertar nuevo) |
| `R` | Herramienta Censurar / Redactar por área |
| `I` | Insertar imagen |
| `L` | Insertar hipervínculo |
| `P` | Herramienta Lápiz / Trazo libre a mano alzada |
| `Shift + H` | Resaltar texto o área seleccionada |
| `Shift + U` | Subrayar texto o área |
| `Shift + K` | Tachar texto o área |
| `N` | Insertar nota adhesiva o comentario |
| `Supr` (Delete) | Eliminar páginas seleccionadas |
| `Alt + Arriba / Abajo` | Mover páginas seleccionadas hacia arriba o abajo |
| `Ctrl + Shift + Izq / Der` | Girar páginas seleccionadas 90° |

---

## Suite de Pruebas Automatizadas

El proyecto incluye una suite de validación automatizada que comprueba todas las operaciones de páginas, edición in situ, motor de OCR, conversiones a formatos externos, compresión, anotaciones y formularios.

Para ejecutarla:
```powershell
.\.venv\Scripts\python.exe tests\test_suite.py
```

---

## Recompilación de la Versión Portable

Si en el futuro modificas algún archivo dentro de `app/` y deseas actualizar el ejecutable de `dist\EditorPDFPortable`, simplemente ejecuta:
```powershell
.\.venv\Scripts\python.exe build_portable.py
```
El script invocará a PyInstaller con los parámetros, iconos y carpetas de datos configurados y actualizará `EditorPDFPortable.exe` automáticamente sin dejar residuos en el directorio.
