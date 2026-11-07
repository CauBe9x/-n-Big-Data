r"""Quản lý một cụm PostgreSQL RIÊNG cho đồ án, không cần Docker và không đụng vào server có sẵn trên máy.

    python scripts/local_db.py start    # khởi tạo (lần đầu) rồi chạy, cổng 5433
    python scripts/local_db.py stop
    python scripts/local_db.py status
    python scripts/local_db.py dump     # sao lưu CSDL ra data/snapshot/vietjobs.dump để demo trên máy khác
    python scripts/local_db.py restore  # khôi phục từ file đó

Dùng chính bộ binary PostgreSQL đã cài (tự tìm trong PATH hoặc C:\Program Files\PostgreSQL\*in; đặt PG_BIN nếu ở
chỗ khác). Thư mục dữ liệu nằm ở %LOCALAPPDATA%\VietJobs\pgdata vì initdb của PostgreSQL không chạy được trên đường
dẫn có dấu tiếng Việt như "Đồ Án BigData".
"""
from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252 không in được tiếng Việt

PORT = int(os.getenv("VIETJOBS_PG_PORT", "5433"))
USER = PASSWORD = DB = "vietjobs"


def _home() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(os.getenv("VIETJOBS_PG_HOME", Path(base) / "VietJobs"))


DATA_DIR = _home() / "pgdata"
LOG_FILE = _home() / "postgres.log"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot" / "vietjobs.dump"


def _bin(name: str) -> str:
    exe = name + (".exe" if os.name == "nt" else "")
    if os.getenv("PG_BIN"):
        return str(Path(os.environ["PG_BIN"]) / exe)
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(glob.glob(os.path.join(r"C:\Program Files\PostgreSQL", "*", "bin", exe)) +
                        glob.glob(f"/usr/lib/postgresql/*/bin/{exe}"))
    if candidates:
        return candidates[-1]
    sys.exit("Không tìm thấy PostgreSQL. Cài từ postgresql.org hoặc đặt biến môi trường PG_BIN.")


def _listening() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def init() -> None:
    if (DATA_DIR / "PG_VERSION").exists():
        return
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"[db] Khởi tạo cụm PostgreSQL tại {DATA_DIR}")
    with tempfile.NamedTemporaryFile("w", suffix=".pw", delete=False) as f:
        f.write(PASSWORD)
    try:
        _run(_bin("initdb"), "-D", str(DATA_DIR), "-U", USER, f"--pwfile={f.name}", "-A", "scram-sha-256",
             "-E", "UTF8", "--locale=C")
    finally:
        os.unlink(f.name)
    with open(DATA_DIR / "postgresql.conf", "a", encoding="utf-8") as conf:
        conf.write(f"\n# VietJobs\nport = {PORT}\nlisten_addresses = '127.0.0.1'\nshared_buffers = 256MB\n"
                   "work_mem = 32MB\nmaintenance_work_mem = 128MB\nsynchronous_commit = off\n")


def start() -> None:
    init()
    if _listening():
        print(f"[db] Đã chạy ở cổng {PORT}")
    else:
        _run(_bin("pg_ctl"), "-D", str(DATA_DIR), "-l", str(LOG_FILE), "-w", "-t", "30", "start")
        print(f"[db] Đã khởi động PostgreSQL ở cổng {PORT}")
    env = {**os.environ, "PGPASSWORD": PASSWORD}
    psql = [_bin("psql"), "-h", "127.0.0.1", "-p", str(PORT), "-U", USER, "-d", "postgres", "-tAc"]
    for name in (DB, "superset"):  # 'superset' là CSDL metadata cho dashboard Superset (tuỳ chọn)
        exists = subprocess.run([*psql, f"SELECT 1 FROM pg_database WHERE datname='{name}'"], env=env, check=True,
                                capture_output=True, text=True).stdout.strip()
        if exists != "1":
            subprocess.run([*psql, f"CREATE DATABASE {name}"], env=env, check=True, stdout=subprocess.DEVNULL)
            print(f"[db] Đã tạo CSDL {name}")


def stop() -> None:
    if not _listening():
        print("[db] Không chạy")
        return
    _run(_bin("pg_ctl"), "-D", str(DATA_DIR), "-m", "fast", "-w", "stop")
    print("[db] Đã dừng")


def _pg_env() -> dict:
    return {**os.environ, "PGPASSWORD": PASSWORD}


def _conn() -> list[str]:
    return ["-h", "127.0.0.1", "-p", str(PORT), "-U", USER, "-d", DB]


def dump() -> None:
    # pg_dump không ghi được vào đường dẫn có dấu tiếng Việt, nên ghi ở thư mục ASCII rồi chép về dự án
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    tmp = _home() / "snapshot.tmp"
    subprocess.run([_bin("pg_dump"), *_conn(), "-Fc", "-f", str(tmp)], env=_pg_env(), check=True)
    shutil.move(str(tmp), SNAPSHOT)
    print(f"[db] Đã lưu {SNAPSHOT} ({SNAPSHOT.stat().st_size / 1e6:.0f} MB)")


def restore() -> None:
    if not SNAPSHOT.exists():
        sys.exit(f"Không có {SNAPSHOT}")
    tmp = _home() / "snapshot.tmp"
    shutil.copyfile(SNAPSHOT, tmp)
    try:
        subprocess.run([_bin("pg_restore"), *_conn(), "--clean", "--if-exists", "--no-owner", "-j", "2", str(tmp)],
                       env=_pg_env(), check=True)
    finally:
        tmp.unlink(missing_ok=True)
    print("[db] Đã khôi phục CSDL từ snapshot")


def status() -> None:
    state = "đang chạy" if _listening() else "đã dừng"
    print(f"[db] {state}, cổng {PORT}, dữ liệu: {DATA_DIR}")


if __name__ == "__main__":
    actions = {"start": start, "stop": stop, "status": status, "dump": dump, "restore": restore}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(f"Dùng: python {Path(__file__).name} {{{'|'.join(actions)}}}")
    actions[sys.argv[1]]()
