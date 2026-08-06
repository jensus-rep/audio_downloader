@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" gui.py
) else (
  pythonw gui.py
)
if errorlevel 1 (
  echo Die Anwendung konnte nicht gestartet werden.
  echo Bitte zuerst die Installationsschritte in README.md ausfuehren.
  pause
)
