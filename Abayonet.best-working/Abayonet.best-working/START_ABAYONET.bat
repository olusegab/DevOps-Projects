@echo off
title AbayoNet Enterprise Monitor v7.0
color 0A
cls
echo.
echo  ================================================================
echo         AbayoNet Enterprise Network Monitor  v7.0
echo         NOC-Grade  .  Multi-User  .  Network Access
echo  ================================================================
echo.

:: ── Check Python ────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  1. Go to: https://python.org/downloads
    echo  2. Download Python 3.10 or newer
    echo  3. During install: CHECK "Add Python to PATH"
    echo  4. Re-run this file
    echo.
    pause
    exit /b 1
)
echo  [OK] Python found.

:: ── Create data folder if missing ───────────────────────────────────
if not exist "data" (
    mkdir data
    echo  [OK] Created data\ folder.
)

:: ── Open firewall port 8780 (silent, needs admin rights) ────────────
netsh advfirewall firewall show rule name="AbayoNet" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Adding Windows Firewall rule for port 8780...
    netsh advfirewall firewall add rule name="AbayoNet" protocol=TCP dir=in localport=8780 action=allow >nul 2>&1
    if errorlevel 1 (
        echo  [WARN] Could not add firewall rule - run as Administrator to allow LAN access.
    ) else (
        echo  [OK] Firewall rule added.
    )
)

:: ── Print access info ────────────────────────────────────────────────
echo.
echo  ----------------------------------------------------------------
echo   ACCESS URLS
echo  ----------------------------------------------------------------
echo   Local machine:   http://127.0.0.1:8780
echo   From LAN / NOC:  http://YOUR-SERVER-IP:8780
echo   From internet:   Forward TCP port 8780 on your router
echo.
echo   (The exact LAN IP will be shown below when server starts)
echo  ----------------------------------------------------------------
echo.
echo   Press Ctrl+C to stop AbayoNet.
echo  ================================================================
echo.

:: ── Launch ──────────────────────────────────────────────────────────
cd /d "%~dp0"
python abayonet.py

echo.
echo  AbayoNet has stopped.
pause
