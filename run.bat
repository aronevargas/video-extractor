@echo off
rem Inicia o Extrator de Videos no Windows (usa .venv, se existir, para ter o yt-dlp).
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
) else (
    where py >nul 2>nul && (py -3 main.py %*) || (python main.py %*)
)
if errorlevel 1 pause
