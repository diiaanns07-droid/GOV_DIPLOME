@echo off
setlocal EnableExtensions
rem Astana civic preview. Explicit synthetic demo, separate persistent database.
cd /d "%~dp0"
set "PORT=8611"
set "CIVIC_DEMO=1"
rem Round 15: one demo world of Astana for every section (R02 world_v1.json). Turned on after the R10 part-1 regression
rem with the world was green (B0.9: 172/0/2). To show the FINAL-4 demo instead: set CIVIC_DEMO_WORLD=0 before running.
if not defined CIVIC_DEMO_WORLD set "CIVIC_DEMO_WORLD=1"
set "CIVIC_DB_PATH=%~dp0.runtime\round11-local.sqlite3"
call "%~dp0run.bat"
exit /b %errorlevel%
