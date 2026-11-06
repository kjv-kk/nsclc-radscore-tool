@echo off
set "PY313=D:\除了文档以外的\农哲的软件\python\python.exe"
if exist "%PY313%" (
  "%PY313%" "%~dp0launch.py"
  exit /b
)
py -3.13 "%~dp0launch.py" 2>nul
if not errorlevel 1 exit /b
python "%~dp0launch.py" 2>nul
if not errorlevel 1 exit /b
echo Python 3.13 with streamlit was not found.
echo Install it, then run:  python "%~dp0launch.py"
pause