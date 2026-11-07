@echo off
REM Chay Superset KHONG can Docker (Windows). Yeu cau: PostgreSQL dang chay, da co CSDL 'superset'.
cd /d %~dp0
if not exist .venv-superset (
  py -3.11 -m venv .venv-superset
  .venv-superset\Scripts\pip install -U pip
  .venv-superset\Scripts\pip install -r requirements-superset.txt
)
set SUPERSET_CONFIG_PATH=%CD%\superset_config.py
set FLASK_APP=superset
.venv-superset\Scripts\superset db upgrade
.venv-superset\Scripts\superset fab create-admin --username admin --password admin --firstname Admin --lastname VietJobs --email admin@vietjobs.local
.venv-superset\Scripts\superset init
echo Superset: http://localhost:8088  (admin / admin)
echo Lan dau: mo terminal khac va chay  python bi\setup_dashboard.py
.venv-superset\Scripts\superset run -h 0.0.0.0 -p 8088 --with-threads
