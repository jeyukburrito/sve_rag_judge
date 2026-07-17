@echo off
rem SVE 룰 저지 GUI 실행 (더블클릭 또는 run.bat [--llm 모델] [--port 포트])
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python -m src.judge_gui %*
pause
