# JARVIS AI Holographic Desktop Launcher
Set-Location -Path $PSScriptRoot
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   Starting JARVIS AI Agent Engine + Holographic Desktop Window...   " -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
uv run jarvis desktop $args
