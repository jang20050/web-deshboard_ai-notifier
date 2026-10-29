@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 서버가 뜰 시간을 준 뒤 브라우저를 연다
start "" /min cmd /c "timeout /t 4 >nul & start http://localhost:8001"
python server.py
pause
