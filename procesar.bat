@echo off
chcp 65001 >nul
title Procesar Listas Hospitalarias
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Listas Hospitalarias Venezuela 2026        ║
echo  ║   Procesador de archivos                     ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── Verificar instalación ─────────────────────────
if not exist "venv\" (
    echo  [!] El programa no esta instalado.
    echo      Haz doble clic en instalar_windows.bat primero.
    pause
    exit /b 1
)

:: ── Cargar API key ────────────────────────────────
if exist "API_CLAUDE_TERREMOTO.txt" (
    set /p ANTHROPIC_API_KEY=<API_CLAUDE_TERREMOTO.txt
)

if "%ANTHROPIC_API_KEY%"=="" (
    echo  [!] No se encontro la API key.
    echo      Haz doble clic en instalar_windows.bat primero.
    pause
    exit /b 1
)

:: ── Pedir carpeta ─────────────────────────────────
echo  Arrastra la carpeta con las fotos/PDFs a esta ventana
echo  y presiona Enter. O escribe la ruta completa.
echo.
set /p CARPETA="  Carpeta: "

:: Quitar comillas si las tiene
set CARPETA=%CARPETA:"=%

if "%CARPETA%"=="" (
    echo.
    echo  [!] No indicaste ninguna carpeta.
    pause
    exit /b 1
)

if not exist "%CARPETA%" (
    echo.
    echo  [!] La carpeta no existe: %CARPETA%
    pause
    exit /b 1
)

:: ── Proceso ───────────────────────────────────────
echo.
echo  Paso 1/3: Descargando estado actual...
venv\Scripts\python sync_bajar.py
echo.

echo  Paso 2/3: Procesando archivos...
echo  ^(esto puede tardar varios minutos segun cuantos archivos haya^)
echo.
venv\Scripts\python procesar_drive.py "%CARPETA%"
echo.

echo  Paso 3/3: Subiendo resultados a la web...
venv\Scripts\python sync_subir.py
echo.

echo  ╔══════════════════════════════════════════════╗
echo  ║   Listo. Los resultados ya estan en:         ║
echo  ║   listashospitalarias.pythonanywhere.com      ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause
