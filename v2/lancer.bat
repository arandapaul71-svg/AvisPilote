@echo off
chcp 65001 >NUL
title AvisPilote
cd /d "%~dp0"
echo.
echo   =============================================
echo     AvisPilote - demarrage
echo   =============================================
echo.
where python >NUL 2>NUL || (echo Python n'est pas installe : telecharge-le sur https://www.python.org puis relance ce fichier. & pause & exit /b 1)
if not exist .venv (
  echo Premiere installation : environ 2 minutes, une seule fois...
  python -m venv .venv || (echo Impossible de creer l'environnement Python. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
echo Verification des composants...
python -m pip install -q --disable-pip-version-check -r requirements.txt || (echo Installation impossible : verifie ta connexion Internet. & pause & exit /b 1)
python manage.py migrate --noinput -v 0 || (echo Mise a jour de la base impossible. & pause & exit /b 1)
echo.
echo   AvisPilote est pret : le navigateur va s'ouvrir sur http://localhost:8000
echo   Clique sur "Decouvrir avec la demo" pour tout voir sans compte.
echo   Pour arreter AvisPilote : ferme cette fenetre.
echo.
start "" cmd /c "timeout /t 3 >NUL & start http://localhost:8000/connexion/"
python manage.py runserver 8000 --noreload
pause
