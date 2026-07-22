@echo off
title BREA Factory -- Start

echo Stopping any existing Factory processes...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im ngrok.exe >nul 2>&1

timeout /t 2 /nobreak >nul

echo Starting Factory Orchestrator...
start /min "BREA Factory" cmd /k "python C:\Users\Danielle\Desktop\BREA_FACTORY\brea_factory.py"

echo Starting Factory Dashboard...
start /min "BREA Dashboard" cmd /k "python C:\Users\Danielle\Desktop\BREA_FACTORY\dashboard\app.py"

echo Starting Brea 3...
start /min "BREA 3" cmd /k "python C:\Users\Danielle\Desktop\BREA_WEBAPP\app.py"

echo Starting BEOS...
start /min "BEOS" cmd /k "python C:\Users\Danielle\Desktop\BEOS_PLATFORM\app.py"

timeout /t 3 /nobreak >nul

echo Starting ngrok tunnels...
start /min "ngrok-factory" cmd /k "ngrok http --url=brea-working.ngrok.app 5003"
start /min "ngrok-brea3" cmd /k "ngrok http --url=brea3.ngrok.app 5000"
start /min "ngrok-boss" cmd /k "ngrok http --url=theboss.ngrok.app 5002"

start https://brea-working.ngrok.app
