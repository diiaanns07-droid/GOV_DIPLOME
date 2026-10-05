@echo off
rem Windows launcher for the city-evidence demo (prototype only; does not touch the main site or run.bat).
rem Needs Python 3 from python.org (py launcher) or "python" on PATH. Not tested on Windows by the author.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 serve.py 8765 --open
) else (
  python serve.py 8765 --open
)
if errorlevel 1 pause
