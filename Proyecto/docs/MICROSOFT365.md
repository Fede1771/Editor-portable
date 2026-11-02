# Creación de PDFs con Microsoft 365 de escritorio

El editor crea PDFs desde documentos de Word, Excel y PowerPoint usando las aplicaciones de escritorio instaladas, mediante COM y pywin32. La exportación se realiza localmente con Office; el comportamiento de sus complementos, activación, documentos vinculados y servicios conectados depende de la configuración del equipo.

## Motores utilizados

| Operación | Implementación |
|---|---|
| Word → PDF | `Documents.Open` como sólo lectura y `ExportAsFixedFormat` al formato 17. |
| Excel → PDF | `Workbooks.Open` sin actualizar enlaces, sólo lectura, cálculo manual; `ExportAsFixedFormat` tipo 0. |
| PowerPoint → PDF | `Presentations.Open` como sólo lectura, sin ventana; `SaveAs` al formato 32. |

El editor está enfocado exclusivamente en la lectura, edición y manipulación de PDFs. La única exportación disponible desde el visor es a imágenes (PNG/JPEG).

## Aislamiento y guardado

- Cada trabajo COM corre en un proceso creado con `multiprocessing.spawn`, inicializado como STA. Los objetos PDF y COM no se comparten entre hilos o procesos.
- Un mutex por aplicación serializa las operaciones entre distintas instancias del editor, incluyendo la activación de PowerPoint.
- Word y Excel se crean con `DispatchEx`. Se identifica la instancia creada antes de abrir el archivo de entrada. PowerPoint es MultiUse: si ya hay un proceso abierto se rechaza el trabajo antes de conectarse a él.
- Si el wrapper Python no expone `Word.Application.Documents`, se consulta `IDispatch` en la misma instancia. Las respuestas de servidor ocupado se reintentan un máximo de ocho veces, con pausas de 250 ms. No se regeneran cachés COM compartidas ni se conecta el trabajo a la sesión activa del usuario.
- Se solicita `AutomationSecurity = 3`, se desactivan eventos de Excel y se evita actualizar enlaces al abrir. No se alteran políticas del Centro de confianza ni se aceptan sus avisos.
- Un timeout termina el trabajador si la aplicación queda bloqueada. La limpieza de Office valida PID, hora de creación y nombre de la instancia registrada; nunca finaliza aplicaciones por nombre de forma global.
- Los avisos identifican la última etapa (inicio, acceso a Documents, apertura, exportación o cierre) y conservan el detalle técnico. Un timeout durante la limpieza no reemplaza el error de conversión.
- La salida a PDF se escribe en un temporal aislado y se valida su estructura antes de publicar el archivo final. Un fallo conserva intacto cualquier destino anterior.

## Dependencias

Se requieren Microsoft 365 de escritorio para Windows, activación válida y las aplicaciones correspondientes (`WINWORD.EXE`, `EXCEL.EXE`, `POWERPNT.EXE`). La versión web de Microsoft 365 no sustituye las aplicaciones locales.

`pywin32` y `psutil` se distribuyen con el ejecutable portable. Microsoft 365 no se incluye en el paquete; el editor funciona de forma totalmente autónoma para leer, editar, anotar, firmar, comprimir, aplicar OCR y exportar a imágenes sin necesidad de tener Office instalado.

## Uso y diagnóstico

Para crear un PDF desde un archivo de Office, usá **Crear PDF desde archivos…** (`Ctrl + N`) o arrastrá el archivo compatible al editor; el resultado se genera en un PDF nuevo que podés revisar y guardar con `Ctrl + S`.

| Problema | Qué revisar |
|---|---|
| No se inicia la aplicación de Office. | Abrila manualmente y comprobá su activación y que no esté esperando configuración inicial. La suscripción web no sustituye la instalación local. |
| PowerPoint ya está abierto. | Guardá tus presentaciones, cerrá PowerPoint y reintentá. |
| Excel exporta un PDF con contenido recortado. | Revisá los anchos de columna, el área de impresión y la escala del archivo de origen en Excel. |
| La conversión supera el tiempo máximo. | Revisá contraseñas, avisos pendientes de Office y restricciones corporativas. |
| `Microsoft 365 (Word): Word.Application.Documents`. | Falló el acceso a la colección de documentos de Word, antes de exportar. El mensaje aislado no identifica una causa única: puede involucrar disponibilidad de COM, metadatos de automatización o la instalación de Office del equipo. Probá el diagnóstico siguiente y entregá el informe a soporte si persiste. |

### Diagnóstico de Word en otro equipo

La autoprueba general `--self-test` no prueba Office. El diagnóstico opcional siguiente sí inicia una instancia aislada de Word y crea un DOCX sintético sin macros ni vínculos. Comprueba que se exporte a un PDF de una página con el texto esperado y que el DOCX no cambie. No abre documentos personales. Conserva el DOCX, el PDF y el informe dentro de la carpeta indicada para poder revisar el resultado.

Desde la raíz del paquete portable extraído, en PowerShell:

```powershell
$check = Start-Process -FilePath '.\EditorPDFPortable.exe' -ArgumentList '--self-test-office', 'diagnostico-word' -Wait -PassThru -WindowStyle Hidden
$check.ExitCode
Get-Content .\diagnostico-word\office_self_test_result.json
```

Desde el repositorio, sin compilar:

```powershell
.\Proyecto\.venv\Scripts\python.exe Proyecto\main.py --self-test-office Proyecto\build\diagnostico-word
Get-Content Proyecto\build\diagnostico-word\office_self_test_result.json
```

El resultado correcto tiene `"ok": true`, `"word_pdf": true` dentro de `checks` y código de salida `0`. Si falla, el JSON incluye la excepción con su etapa y detalle técnico. Este ensayo sólo comprueba **Word → PDF**; no certifica Excel, PowerPoint ni todos los documentos posibles. Requiere una compilación que incluya esta opción.

En un equipo corporativo, abrí Word manualmente para comprobar activación y avisos iniciales. Si el diagnóstico sigue fallando, pedí al área de soporte que revise la instalación, el registro COM y las políticas de automatización de Office. No es necesario desactivar el Centro de confianza ni ejecutar el editor como administrador para aplicar una supuesta solución genérica.

## Referencias

- [Seguridad de automatización de Excel y límite con macros XLM](https://learn.microsoft.com/en-us/office/vba/api/excel.application.automationsecurity).
- [Seguridad de automatización de PowerPoint](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.application.automationsecurity).
- [Instancias SingleUse y MultiUse de Office](https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/use-visual-c-automate-run-program-instance).
- [Objeto Application de Word](https://learn.microsoft.com/en-us/office/vba/api/word.application).
- [Implementación del acceso dinámico a COM en pywin32](https://github.com/mhammond/pywin32/blob/main/com/win32com/client/dynamic.py).
