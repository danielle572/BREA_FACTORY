@echo off
setlocal enabledelayedexpansion
title BREA Factory -- Setup

echo ============================================================
echo  BREA Factory Setup
echo ============================================================
echo.

:: ── Python check ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and re-run this script.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── pip packages ─────────────────────────────────────────────
echo.
echo Installing required packages...
python -m pip install --upgrade pip --quiet
python -m pip install flask flask-socketio requests python-dotenv anthropic ^
    "python-socketio[client]" eventlet watchdog --quiet

if errorlevel 1 (
    echo [ERROR] Package installation failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] All packages installed.

:: ── .env check ───────────────────────────────────────────────
echo.
if exist "%~dp0.env" (
    echo [OK] .env file found.
) else (
    echo [WARN] .env file missing. Copy your credentials to:
    echo        %~dp0.env
    echo        Required keys: AIRTABLE_TOKEN, FACTORY_BASE_ID,
    echo                       ANTHROPIC_API_KEY, DEEPGRAM_API_KEY,
    echo                       ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
)

:: ── ngrok check ──────────────────────────────────────────────
echo.
where ngrok >nul 2>&1
if errorlevel 1 (
    echo [WARN] ngrok not found in PATH. Download from https://ngrok.com/download
    echo        and add it to your PATH before running Start_Factory.bat.
) else (
    for /f "tokens=*" %%v in ('ngrok version 2^>^&1') do echo [OK] %%v
)

:: ── Done ─────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Setup complete. Run Start_Factory.bat to launch.
echo ============================================================
echo.
pause
