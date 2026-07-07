@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
rem concurrency=2 is the reliable max; higher may trigger platform contract-creation rate limit
".venv\Scripts\python.exe" -u upload_videos_minimal.py --concurrency 2
pause
