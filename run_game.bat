@echo off
echo Iniciando el Simulador del Juego de la Cerveza...
cd /d "%~dp0"
python -m streamlit run app.py
pause
