@echo off
if exist "%~dp0EditorPDFPortable.exe" (
    start "" "%~dp0EditorPDFPortable.exe" %*
) else if exist "%~dp0EditorPDFPortable\EditorPDFPortable.exe" (
    start "" "%~dp0EditorPDFPortable\EditorPDFPortable.exe" %*
) else if exist "%~dp0dist\EditorPDFPortable\EditorPDFPortable.exe" (
    start "" "%~dp0dist\EditorPDFPortable\EditorPDFPortable.exe" %*
) else (
    echo No se encontro EditorPDFPortable.exe
    exit /b 1
)
