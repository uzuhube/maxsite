@echo off
chcp 65001 >nul 2>&1
echo ╔══════════════════════════════════════╗
echo ║   GeoSolver — CDP Mode              ║
echo ║   100%% accuracy for Steam           ║
echo ╚══════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install from https://python.org
    pause
    exit /b
)

:: Install deps
echo [*] Checking dependencies...
pip install websocket-client requests Pillow >nul 2>&1

:: Launch
echo [*] Starting GeoSolver...
echo.
echo Setup:
echo   Steam → GeoGuessr → Properties → Launch Options:
echo   --remote-debugging-port=34788 --remote-allow-origins=*
echo.
python "%~dp0cdp_solver.py"
pause
