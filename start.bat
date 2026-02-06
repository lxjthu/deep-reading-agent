@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

title Deep Reading Agent - Launcher

echo ============================================
echo   Deep Reading Agent - One-Click Launcher
echo ============================================
echo.

:: ── Step 1: Locate Python ─────────────────────
echo [1/5] Searching for Python ...

:: Try py launcher first (official Windows installer)
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%i in ('py -3 --version 2^>^&1') do set PY_VER=%%i
    set PYTHON_CMD=py -3
    echo       Found: !PY_VER! (py launcher)
    goto :python_found
)

:: Try python command
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
    set PYTHON_CMD=python
    echo       Found: !PY_VER!
    goto :python_found
)

:: Try python3 command
where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%i in ('python3 --version 2^>^&1') do set PY_VER=%%i
    set PYTHON_CMD=python3
    echo       Found: !PY_VER!
    goto :python_found
)

echo [ERROR] Python not found!
echo         Please install Python 3.10+ from https://www.python.org/downloads/
echo         Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:python_found

:: ── Step 2: Create / activate virtual environment ──
echo.
echo [2/5] Setting up virtual environment ...

set VENV_DIR=%~dp0venv
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe
set VENV_PIP=%VENV_DIR%\Scripts\pip.exe

if exist "%VENV_PYTHON%" (
    echo       Virtual environment already exists.
) else (
    echo       Creating virtual environment ...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo       Virtual environment created.
)

:: Activate venv
call "%VENV_DIR%\Scripts\activate.bat"

:: ── Step 3: Install / update dependencies ─────
echo.
echo [3/5] Installing dependencies ...

set REQ_FILE=%~dp0requirements.txt
if not exist "%REQ_FILE%" (
    echo [ERROR] requirements.txt not found!
    pause
    exit /b 1
)

:: Use a stamp file to avoid reinstalling every time
set STAMP_FILE=%VENV_DIR%\.req_stamp
set NEED_INSTALL=0

if not exist "%STAMP_FILE%" (
    set NEED_INSTALL=1
) else (
    :: Compare timestamps: if requirements.txt is newer, reinstall
    for /f "tokens=*" %%a in ("%REQ_FILE%") do set REQ_TIME=%%~ta
    for /f "tokens=*" %%a in ("%STAMP_FILE%") do set STAMP_TIME=%%~ta
    if "!REQ_TIME!" neq "!STAMP_TIME!" set NEED_INSTALL=1
)

if !NEED_INSTALL!==1 (
    echo       Installing packages from requirements.txt ...
    "%VENV_PIP%" install -r "%REQ_FILE%" --quiet
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Some packages may have failed to install.
        echo           The GUI may still work if core packages are present.
    ) else (
        echo       All packages installed successfully.
    )
    :: Update stamp
    copy /y "%REQ_FILE%" "%STAMP_FILE%" >nul 2>&1
) else (
    echo       Dependencies are up to date.
)

:: ── Step 4: Check .env configuration ──────────
echo.
echo [4/5] Checking environment configuration ...

set ENV_FILE=%~dp0.env
if exist "%ENV_FILE%" (
    echo       .env file found.
    :: Check if DEEPSEEK_API_KEY is set (not just commented out)
    findstr /r /c:"^DEEPSEEK_API_KEY=." "%ENV_FILE%" >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo       [WARNING] DEEPSEEK_API_KEY is not configured.
        echo       Opening configuration dialog ...
        "%VENV_PYTHON%" "%~dp0setup_env.py"
    )
) else (
    echo       .env file not found. Opening configuration dialog ...
    "%VENV_PYTHON%" "%~dp0setup_env.py"
    if %ERRORLEVEL% neq 0 (
        echo       Configuration was cancelled. Starting anyway ...
    )
)

:: ── Step 5: Launch GUI ────────────────────────
echo.
echo [5/5] Starting Deep Reading Agent GUI ...
echo.
echo       URL: http://127.0.0.1:7860
echo       Press Ctrl+C in this window to stop the server.
echo ============================================
echo.

:: Open browser after a short delay (in background)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:7860"

:: Launch the app (blocking)
"%VENV_PYTHON%" "%~dp0app.py"

:: If we get here, the server has stopped
echo.
echo Deep Reading Agent has stopped.
pause
