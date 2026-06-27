@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Instalador - Listas Hospitalarias Venezuela
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Listas Hospitalarias Venezuela 2026        ║
echo  ║   Instalador - Solo correr una vez           ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── Verificar Python ──────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python no está instalado.
    echo.
    echo      1. Abre el navegador y ve a: https://www.python.org/downloads/
    echo      2. Descarga la version mas reciente
    echo      3. Durante la instalacion, marca la casilla:
    echo         "Add Python to PATH"  ^<-- MUY IMPORTANTE
    echo      4. Cierra esta ventana y vuelve a abrirla
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] Python %PY_VER% encontrado.

:: ── Crear entorno virtual ─────────────────────────
if not exist "venv\" (
    echo  [..] Preparando entorno...
    python -m venv venv >nul 2>&1
    echo  [OK] Entorno creado.
) else (
    echo  [OK] Entorno ya existe.
)

:: ── Instalar dependencias ─────────────────────────
echo  [..] Instalando programas necesarios ^(puede tardar 2-3 minutos^)...
venv\Scripts\pip install --quiet --upgrade pip >nul 2>&1
venv\Scripts\pip install --quiet anthropic flask werkzeug rapidfuzz pillow pymupdf python-docx
if errorlevel 1 (
    echo.
    echo  [!] Error instalando dependencias.
    echo      Verifica que tienes conexion a internet e intenta de nuevo.
    pause
    exit /b 1
)
echo  [OK] Todo instalado correctamente.

:: ── API Key de Anthropic ─────────────────────────
if exist "API_CLAUDE_TERREMOTO.txt" (
    echo  [OK] API key de Anthropic encontrada.
) else (
    echo.
    echo  ── API Key de Anthropic ──────────────────────
    echo  Pidele a Simon que te la envie.
    echo.
    set /p APIKEY="  Pega la API key de Anthropic y presiona Enter: "
    if "!APIKEY!"=="" (
        echo  [!] No ingresaste ninguna key. Vuelve a correr este instalador.
        pause
        exit /b 1
    )
    echo !APIKEY!> API_CLAUDE_TERREMOTO.txt
    echo  [OK] API key guardada.
)

:: ── Token de PythonAnywhere ───────────────────────
if exist "PA_TOKEN.txt" (
    echo  [OK] Token de sincronizacion encontrado.
) else (
    echo.
    echo  ── Token de sincronizacion ───────────────────
    echo  Pidele a Simon que te lo envie.
    echo.
    set /p PATOKEN="  Pega el token y presiona Enter: "
    if "!PATOKEN!"=="" (
        echo  [!] No ingresaste el token. Vuelve a correr este instalador.
        pause
        exit /b 1
    )
    echo !PATOKEN!> PA_TOKEN.txt
    echo  [OK] Token guardado.
)

:fin
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Instalacion completada con exito           ║
echo  ║                                              ║
echo  ║   Para procesar archivos:                    ║
echo  ║   Haz doble clic en:  procesar.bat           ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause
