@echo off
title Galvor Social Studio
cd /d "%~dp0"
rem Start the Cloudflare Tunnel (team access) if it has been set up with tools\setup_tunnel.ps1
if exist "data\tunnel.yml" (
  where cloudflared >nul 2>nul && start "Galvor Studio tunnel" /min cloudflared tunnel --config "data\tunnel.yml" run
)
start "" http://localhost:5055
rem Python 3.15 has the studio's packages (Flask, pandas, openpyxl); fall back to whatever python is on PATH
where py >nul 2>nul && (py -3.15 app.py) || (python app.py)
pause
