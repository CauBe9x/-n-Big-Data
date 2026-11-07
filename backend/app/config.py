"""Cấu hình: đọc từ biến môi trường hoặc file .env ở thư mục gốc dự án."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Nạp .env đơn giản (KEY=VALUE), không ghi đè biến đã có trong môi trường."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")

RAW_CSV = Path(os.getenv("VIETJOBS_CSV", ROOT_DIR / "data" / "raw" / "VietJobs.csv"))
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
ARTIFACTS_DIR = Path(os.getenv("VIETJOBS_ARTIFACTS", BACKEND_DIR / "artifacts"))

# PostgreSQL (khởi động bằng: docker compose up -d postgres)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://vietjobs:vietjobs@localhost:5432/vietjobs")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Địa chỉ dashboard BI (Superset) – frontend hiển thị liên kết tới đây
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8088/superset/dashboard/vietjobs/")

# Spark: kết quả JSON để API đọc nằm trong dự án (data/lake); Parquet và môi trường Python của Spark nằm ở đường dẫn
# ASCII vì JVM trên Windows không xử lý được thư mục có dấu tiếng Việt (xem spark/spark_pipeline.py)
LAKE_DIR = ROOT_DIR / "data" / "lake"
_LOCAL_BASE = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local" / "share")
SPARK_HOME_DIR = Path(os.getenv("VIETJOBS_SPARK_HOME", _LOCAL_BASE / "VietJobs"))
SPARK_PYTHON = SPARK_HOME_DIR / "spark-venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

RANDOM_STATE = 42
