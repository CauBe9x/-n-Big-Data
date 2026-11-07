r"""Tạo môi trường Python riêng cho Spark ở %LOCALAPPDATA%\VietJobs\spark-venv (đường dẫn ASCII).

Không cài pyspark vào backend/.venv: JVM trên Windows treo khi đường dẫn có dấu tiếng Việt ("Đồ Án BigData").
Cần Java 17 trở lên. Đã kiểm thử với Spark 4.3.0 + Temurin 25.

    python scripts/setup_spark.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOME = Path(os.getenv("VIETJOBS_SPARK_HOME") or Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local/share") / "VietJobs")
VENV = HOME / "spark-venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PACKAGES = ["pyspark==4.3.0", "pyarrow", "pandas<3"]  # PySpark 4.3 cảnh báo chưa hỗ trợ đủ pandas 3


def main() -> None:
    if shutil.which("java") is None and not os.getenv("JAVA_HOME"):
        sys.exit("Không tìm thấy Java. Cài JDK 17+ (ví dụ Temurin) rồi chạy lại.")
    HOME.mkdir(parents=True, exist_ok=True)
    if not PY.exists():
        print(f"Tạo môi trường {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True, cwd=HOME)
    print("Cài", ", ".join(PACKAGES))
    subprocess.run([str(PY), "-m", "pip", "install", "-q", *PACKAGES], check=True, cwd=HOME)
    print("Xong. Chạy thử: cd backend && python -m pipeline.spark_job")


if __name__ == "__main__":
    main()
