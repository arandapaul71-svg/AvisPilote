@echo off
title AvisPilote
cd /d "%~dp0"
where python >NUL 2>NUL || (echo Python n'est pas installe : telecharge-le sur https://www.python.org puis relance ce fichier. & pause & exit /b 1)
if not exist .venv (echo Premiere installation, patiente une minute... & python -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
echo.
echo AvisPilote demarre sur http://localhost:5000 - ferme cette fenetre pour l'arreter.
start "" cmd /c "timeout /t 3 >NUL & start http://localhost:5000"
python app.py
pause
