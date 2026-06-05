@echo off
chcp 65001 >nul 2>&1

:: Request admin if not already
net session >nul 2>&1
if errorlevel 1 (
    echo [*] Requesting admin privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo   ╔═══════════════════════════════════════════╗
echo   ║  GeoSolver — CDP Mode (100%% accuracy)    ║
echo   ╚═══════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python не найден! Установите: https://python.org
    pause
    exit /b
)

:: Install deps
echo [*] Проверка зависимостей...
pip install websocket-client requests Pillow >nul 2>&1

echo [*] Зависимости OK
echo.
echo ══════════════════════════════════════════════
echo   ВАЖНО: Настройте Steam!
echo   GeoGuessr → ПКМ → Свойства → Параметры запуска:
echo   --remote-debugging-port=34788 --remote-allow-origins=*
echo ══════════════════════════════════════════════
echo.

python "%~dp0cdp_solver.py"
pause
