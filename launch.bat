@echo off
title Podcast Generator
cd /d "%~dp0"

echo ============================================
echo    Demarrage du Podcast Generator...
echo ============================================

:: Verifier si Ollama tourne deja
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
    echo [1/2] Demarrage d'Ollama...
    start /min "Ollama" ollama serve
    timeout /t 3 /nobreak >NUL
) else (
    echo [1/2] Ollama deja en cours d'execution.
)

:: Lancer l'application Electron (qui demarre automatiquement les backends Python)
echo [2/2] Lancement de l'application...
cd frontend
npm run dev

exit
