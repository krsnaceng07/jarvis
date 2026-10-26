@echo off
title JARVIS AI Holographic Desktop
cd /d "%~dp0"
echo =====================================================================
echo   Starting JARVIS AI Agent Engine + Holographic Desktop Window...
echo =====================================================================
uv run jarvis desktop %*
if %ERRORLEVEL% NEQ 0 (
    echo [JARVIS] Fallback to direct desktop module...
    uv run python -m jarvis_desktop %*
)
pause
