@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title AbayoNet Manager

:: ── Preflight: make sure Python is available ─────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [ERROR] Python was not found on this system's PATH.
    echo  Install Python from https://python.org ^(check "Add to PATH"
    echo  during setup^), then run this script again.
    echo.
    pause
    exit /b 1
)

:: ── Preflight: make sure pymysql is available ────────────────────
:: Checked every time the menu loads (not just on option 7), so
:: picking "Run now" or "Install as Service" on a fresh machine works
:: immediately instead of crashing with ModuleNotFoundError.
python -c "import pymysql" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  First-time setup: installing required Python package ^(pymysql^)...
    python -m pip install --quiet pymysql
    if errorlevel 1 (
        echo.
        echo  [ERROR] Could not install pymysql automatically.
        echo  Try running this file as Administrator, or install it
        echo  manually with:  python -m pip install pymysql
        echo.
        pause
        exit /b 1
    )
    echo  Done.
)

:menu
cls
echo ============================================================
echo   AbayoNet Enterprise Monitor - Manager
echo ============================================================
echo.
echo   1. Run now  ^(no install - runs in this window, closes on exit^)
echo   2. Install as Windows Service ^(starts automatically on boot^)
echo   3. Uninstall Windows Service
echo   4. Start Service
echo   5. Stop Service
echo   6. Reset admin password ^(back to: admin123^)
echo   7. Install/repair Python dependencies ^(pymysql, pywin32^)
echo   8. Exit
echo.
set /p choice="Choose an option (1-8): "

if "%choice%"=="1" goto run_now
if "%choice%"=="2" goto install_service
if "%choice%"=="3" goto uninstall_service
if "%choice%"=="4" goto start_service
if "%choice%"=="5" goto stop_service
if "%choice%"=="6" goto reset_admin
if "%choice%"=="7" goto install_deps
if "%choice%"=="8" goto end
echo.
echo  Not a valid option — pick a number from 1 to 8.
pause
goto menu

:run_now
cls
echo ============================================================
echo   Running AbayoNet in this window.
echo   Close this window, or press Ctrl+C, to stop it.
echo   (This does NOT install anything or run in the background —
echo    it only runs while this window stays open.)
echo ============================================================
echo.
python abayonet.py
echo.
echo  AbayoNet has stopped.
pause
goto menu

:install_service
cls
echo ============================================================
echo   Installing AbayoNet as a Windows Service
echo ============================================================
echo   This needs Administrator rights. If nothing happens or you
echo   see an "Access is denied" error below, close this window and
echo   re-run AbayoNet.bat by right-clicking it and choosing
echo   "Run as administrator".
echo.
python -c "import win32serviceutil" >nul 2>nul
if errorlevel 1 (
    echo  Installing required package ^(pywin32^)...
    python -m pip install --quiet pywin32
    python -m pip install --quiet pywin32-ctypes >nul 2>nul
    echo  Done.
    echo.
)
python abayonet_service.py install
if errorlevel 1 (
    echo.
    echo  Install failed - see the error above.
    echo  Most common cause: pywin32 is not installed yet.
    echo  Try option 7 ^(Install/repair Python dependencies^) first.
    pause
    goto menu
)
echo.
echo  Installed. Starting it now...
python abayonet_service.py start
echo.
echo  Done. AbayoNet will now also start automatically whenever
echo  Windows starts. Open your browser to http://localhost:8780
pause
goto menu

:uninstall_service
cls
echo ============================================================
echo   Uninstalling the AbayoNet Windows Service
echo ============================================================
echo   This needs Administrator rights (see note above if it fails).
echo   Your database and settings are NOT deleted - only the
echo   Windows Service registration is removed.
echo.
set /p confirm="Type YES to confirm uninstall: "
if /i not "%confirm%"=="YES" (
    echo  Cancelled - nothing was changed.
    pause
    goto menu
)
python abayonet_service.py stop
python abayonet_service.py remove
echo.
echo  Service uninstalled.
pause
goto menu

:start_service
cls
echo ============================================================
echo   Starting AbayoNet Service
echo ============================================================
python abayonet_service.py start
echo.
echo  If you see "service is not installed", use option 2 first.
pause
goto menu

:stop_service
cls
echo ============================================================
echo   Stopping AbayoNet Service
echo ============================================================
python abayonet_service.py stop
echo.
pause
goto menu

:reset_admin
cls
echo ============================================================
echo   Reset Admin Password
echo ============================================================
echo   This connects to your configured MySQL database (see
echo   abayonet.cfg) and resets the 'admin' account password
echo   back to the default: admin123
echo   Log in and change it immediately afterwards.
echo.
set /p confirm="Type YES to confirm reset: "
if /i not "%confirm%"=="YES" (
    echo  Cancelled - nothing was changed.
    pause
    goto menu
)
python abayonet.py --reset-admin
pause
goto menu

:install_deps
cls
echo ============================================================
echo   Installing/repairing Python dependencies
echo ============================================================
echo   Installs: pymysql (MySQL driver), pywin32 (Windows Service
echo   support). Safe to re-run any time.
echo.
python -m pip install --upgrade pip
python -m pip install pymysql pywin32
echo.
echo  Done.
pause
goto menu

:end
echo.
echo  Goodbye.
endlocal
exit /b 0
