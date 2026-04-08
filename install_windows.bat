@echo off
REM install_windows.bat — Set up voice-transcriber on Windows.
REM
REM Prerequisites:
REM   - Python 3.10+ on PATH (python or python3)
REM   - ffmpeg on PATH (download from https://ffmpeg.org/download.html)
REM
REM This script:
REM   1. Creates a .venv virtual environment
REM   2. Installs openai-whisper, sounddevice, numpy
REM   3. Creates a voice-transcriber.bat wrapper

setlocal enabledelayedexpansion

echo.
echo === Voice Transcriber — Windows Installer ===
echo.

REM --- Locate Python ---
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
) else (
    where python3 >nul 2>&1
    if %errorlevel%==0 (
        set PYTHON=python3
    ) else (
        echo ERROR: Python not found. Install Python 3.10+ from https://www.python.org
        exit /b 1
    )
)

%PYTHON% --version
echo.

REM --- Check ffmpeg ---
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: ffmpeg not found on PATH.
    echo Whisper requires ffmpeg. Download from https://ffmpeg.org/download.html
    echo and add it to your PATH before using voice-transcriber.
    echo.
)

REM --- Create venv ---
if not exist ".venv" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
)

REM --- Install dependencies ---
echo Installing dependencies...
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install "openai-whisper>=20250625" sounddevice numpy
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    exit /b 1
)

REM --- Create wrapper script ---
set "PROJECT_DIR=%~dp0"
set "WRAPPER=%USERPROFILE%\.local\bin\voice-transcriber.bat"

if not exist "%USERPROFILE%\.local\bin" mkdir "%USERPROFILE%\.local\bin"

echo @echo off> "%WRAPPER%"
echo "%PROJECT_DIR%.venv\Scripts\python" "%PROJECT_DIR%transcriber.py" %%*>> "%WRAPPER%"

echo.
echo === Installation complete ===
echo.
echo Wrapper installed to: %WRAPPER%
echo.
echo Make sure %USERPROFILE%\.local\bin is in your PATH:
echo   setx PATH "%%PATH%%;%USERPROFILE%\.local\bin"
echo.
echo Usage:
echo   voice-transcriber --clipboard
echo   voice-transcriber -m small --clipboard
echo.

endlocal
