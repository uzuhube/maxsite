@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Building executable...
pyinstaller --onefile --windowed --name "AFK Fishing Macro" main.py
echo.
echo Done! Check the dist\ folder.
pause
