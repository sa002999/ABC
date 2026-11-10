@echo off
setlocal

start "KINU TABI Backend" /D "%~dp0backend" cmd /k uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
@REM  start "KINU TABI Try-on Worker" /D "%~dp0backend" cmd /k uv run python manage.py try-on-worker
start "KINU TABI Frontend" /D "%~dp0frontend" cmd /k npm run dev
@REM  start "KINU TABI MCP Server" /D "%~dp0mcp-server" cmd /k npm start