@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   TikTok Drama Center - Environment Setup
echo   run once on a new machine
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo === Setup FAILED. See messages above. ===
) else (
  echo.
  echo === Setup OK. See README.txt, then run the upload .bat. ===
)
pause
