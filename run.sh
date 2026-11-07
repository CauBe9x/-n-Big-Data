#!/usr/bin/env bash
# Khởi động toàn bộ ứng dụng trên localhost (macOS / Linux). Xem scripts/start.py.
# Yêu cầu: Python 3.12, Node.js 18+, PostgreSQL (cài sẵn, hoặc đặt DATABASE_URL trong .env).
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1
exec python3 scripts/start.py "$@"
