@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem AI 작업 알림 bridge 실행 (UNO COM5 + 웹캠 제스처)
python main.py %*
pause
