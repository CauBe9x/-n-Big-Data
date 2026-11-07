@echo off
chcp 65001 >nul
REM Khoi dong toan bo ung dung tren localhost (Windows). Xem scripts\start.py.
REM Yeu cau: Python 3.12, Node.js 18+, PostgreSQL da cai (khong can Docker).
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul && py -3.12 -V >nul 2>nul && (
  py -3.12 scripts\start.py %*
  goto :eof
)
python scripts\start.py %*
