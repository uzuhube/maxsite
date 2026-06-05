@echo off
echo ==============================
echo  GeoGuessr Solver - Proxy Mode
echo ==============================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install from https://python.org
    pause
    exit /b
)

:: Install deps
echo [*] Installing dependencies...
pip install mitmproxy requests Pillow pynput >nul 2>&1

:: Check mitmproxy
mitmdump --version >nul 2>&1
if errorlevel 1 (
    echo [*] Installing mitmproxy...
    pip install mitmproxy
)

:: Enable system proxy
echo [*] Enabling system proxy (127.0.0.1:8082)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "127.0.0.1:8082" /f >nul

:: Start solver
echo [*] Starting GeoGuessr Solver...
echo [*] Close this window to stop and disable proxy.
echo.
python "%~dp0proxy_solver.py"

:: Disable system proxy on exit
echo [*] Disabling system proxy...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
echo [*] Done!
pause
