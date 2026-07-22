@echo off
taskkill /f /im python.exe
taskkill /f /im ngrok.exe
echo All Factory services stopped.
pause
