@echo off
rem Stop the Rad-score server (kills the process listening on port 8501).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /c:":8501 " ^| findstr /c:"LISTENING"') do taskkill /f /pid %%p >nul 2>&1
