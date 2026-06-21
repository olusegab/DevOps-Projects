@echo off
title AbayoNet Enterprise Monitor v3.0
color 0A
cls
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║        AbayoNet Enterprise Monitor v3.0            ║
echo  ║        Professional Network Monitoring            ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Please install Python from: https://python.org/downloads
    echo  During install, CHECK the box "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
echo  Python found.
echo.
echo  Starting AbayoNet...
echo  Your browser will open automatically in a few seconds.
echo.
echo  ► Dashboard: http://127.0.0.1:8765
echo.
echo  Press Ctrl+C to stop AbayoNet.
echo  ─────────────────────────────────────────────────────
echo.
cd /d "%~dp0"
python abayonet.py
echo.
echo  AbayoNet has stopped.
pause
