@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 ( set PY=py ) else ( set PY=python )
echo Verificando dependencias...
%PY% -m pip install -q -r requirements.txt
echo Iniciando la app de picking (se abre en el navegador)...
%PY% -m streamlit run app.py
pause
