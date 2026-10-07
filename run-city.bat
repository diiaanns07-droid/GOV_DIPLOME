@echo off
setlocal EnableExtensions
rem Astana civic preview. Explicit synthetic demo, separate persistent database.
cd /d "%~dp0"
set "PORT=8611"
set "CIVIC_DEMO=1"
set "CIVIC_DB_PATH=%~dp0.runtime\round11-local.sqlite3"
call "%~dp0run.bat"
exit /b %errorlevel%
