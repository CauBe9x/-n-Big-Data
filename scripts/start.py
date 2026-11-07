"""Khởi động toàn bộ ứng dụng bằng một lệnh. Chạy lại nhiều lần được: bước nào đã xong thì bỏ qua.

    python scripts/start.py            # http://localhost:8000
    python scripts/start.py --no-open  # không tự mở trình duyệt

Thứ tự: môi trường Python -> PostgreSQL -> dữ liệu và mô hình -> frontend -> API.
Dữ liệu: nếu CSDL trống thì khôi phục từ data/snapshot (khoảng 1 phút), không có snapshot thì chạy toàn bộ pipeline (20-40 phút).
Chỉ dùng thư viện chuẩn vì script chạy trước khi có môi trường ảo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SNAPSHOT = ROOT / "data" / "snapshot" / "vietjobs.dump"
PORT = int(os.getenv("VIETJOBS_PORT", "8000"))
URL = f"http://localhost:{PORT}"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}


def step(msg: str) -> None:
    print(f"\n>> {msg}", flush=True)


def run(*cmd, cwd=ROOT, check=True) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], cwd=cwd, env=ENV, check=check)


def ensure_python() -> None:
    if not VENV_PY.exists():
        step("Tạo môi trường Python (backend/.venv)")
        run(sys.executable, "-m", "venv", BACKEND / ".venv")
    marker = BACKEND / ".venv" / ".deps-ok"
    lock = BACKEND / "requirements.lock.txt"
    if not marker.exists() or marker.stat().st_mtime < lock.stat().st_mtime:
        step("Cài thư viện Python (lần đầu mất vài phút)")
        run(VENV_PY, "-m", "pip", "install", "-q", "-r", lock)
        marker.touch()


def ensure_env() -> None:
    if not (ROOT / ".env").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")


def uses_local_db() -> bool:
    text = (ROOT / ".env").read_text(encoding="utf-8")
    return ":5433/" in text


def ensure_database() -> None:
    if uses_local_db():
        step("Khởi động PostgreSQL riêng (cổng 5433)")
        run(VENV_PY, ROOT / "scripts" / "local_db.py", "start")
    else:
        step("Dùng PostgreSQL theo DATABASE_URL trong .env")


def db_state() -> tuple[bool, bool]:
    """(có dữ liệu tin tuyển dụng, có kết quả máy học)."""
    code = ("from sqlalchemy import text\nfrom app.db import engine\n"
            "with engine.connect() as c:\n"
            "    jobs = c.execute(text(\"SELECT to_regclass('public.jobs') IS NOT NULL\")).scalar() and "
            "c.execute(text('SELECT count(*) FROM jobs')).scalar() > 0\n"
            "    ml = jobs and c.execute(text('SELECT count(*) FROM job_clusters')).scalar() > 0\n"
            "print(int(bool(jobs)), int(bool(ml)))\n")
    out = subprocess.run([str(VENV_PY), "-c", code], cwd=BACKEND, env=ENV, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("Không kết nối được CSDL:\n" + out.stderr[-600:])
    a, b = out.stdout.split()
    return a == "1", b == "1"


def ensure_data() -> None:
    jobs, ml = db_state()
    models = all((BACKEND / "artifacts" / f"{n}_model.joblib").exists() for n in ("salary", "skills", "category"))
    if jobs and ml and models:
        print("   Dữ liệu và mô hình đã sẵn sàng")
        return
    if SNAPSHOT.exists() and models and uses_local_db():
        step("Khôi phục dữ liệu từ snapshot")
        run(VENV_PY, ROOT / "scripts" / "local_db.py", "restore")
        return
    step("Chạy toàn bộ pipeline (20-40 phút, chỉ cần làm một lần)")
    run(VENV_PY, "-m", "pipeline.run_all", cwd=BACKEND)


def ensure_frontend() -> None:
    dist = FRONTEND / "dist" / "index.html"
    newest = max((p.stat().st_mtime for p in (FRONTEND / "src").rglob("*") if p.is_file()), default=0)
    if dist.exists() and dist.stat().st_mtime >= newest:
        return
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("Không tìm thấy Node.js/npm. Cài Node.js 18+ rồi chạy lại.")
    if not (FRONTEND / "node_modules").exists():
        step("Cài thư viện frontend")
        run(npm, "install", cwd=FRONTEND)
    step("Build frontend")
    run(npm, "run", "build", cwd=FRONTEND)


def open_when_ready(should_open: bool) -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=2) as r:
                if r.status == 200:
                    print(f"\n   Ứng dụng: {URL}\n   Tài liệu API: {URL}/docs\n   Dừng: Ctrl+C, rồi chạy stop.bat để tắt CSDL\n", flush=True)
                    if should_open:
                        webbrowser.open(URL)
                    return
        except OSError:
            time.sleep(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if sys.version_info < (3, 12):
        sys.exit("Cần Python 3.12 trở lên (numpy và pandas đã khoá phiên bản yêu cầu vậy). Tải tại python.org.")
    ensure_python()
    ensure_env()
    ensure_database()
    ensure_data()
    ensure_frontend()
    step(f"Khởi động API tại {URL}")
    threading.Thread(target=open_when_ready, args=(not args.no_open,), daemon=True).start()
    try:
        run(VENV_PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", PORT, cwd=BACKEND)
    except KeyboardInterrupt:
        print("\nĐã dừng API. CSDL vẫn chạy nền; tắt bằng stop.bat hoặc: python scripts/local_db.py stop")


if __name__ == "__main__":
    main()
