#!/usr/bin/env bash
# Chạy Superset KHÔNG cần Docker (macOS / Linux). Yêu cầu: PostgreSQL đang chạy, đã có CSDL 'superset'.
#   psql -U postgres -c "CREATE DATABASE superset OWNER vietjobs;"    (chỉ lần đầu)
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3.11}
if [ ! -d .venv-superset ]; then
  echo ">> Tạo môi trường Superset ($PY)"
  $PY -m venv .venv-superset
  .venv-superset/bin/pip install -U pip
  .venv-superset/bin/pip install -r requirements-superset.txt
fi
export SUPERSET_CONFIG_PATH="$PWD/superset_config.py" FLASK_APP=superset
SS=.venv-superset/bin/superset
$SS db upgrade
$SS fab create-admin --username admin --password admin --firstname Admin --lastname VietJobs \
  --email admin@vietjobs.local || true
$SS init
echo ">> Superset: http://localhost:8088  (admin / admin)"
echo ">> Lần đầu: mở terminal khác và chạy  python bi/setup_dashboard.py  để dựng dashboard"
$SS run -h 0.0.0.0 -p 8088 --with-threads
