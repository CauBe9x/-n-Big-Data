@echo off
chcp 65001 >nul
REM Tat cum PostgreSQL rieng cua do an (cong 5433). Khong dung vao PostgreSQL co san tren may.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist backend\.venv\Scripts\python.exe (
  backend\.venv\Scripts\python scripts\local_db.py stop
) else (
  python scripts\local_db.py stop
)
