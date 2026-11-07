"""Chạy tầng Spark từ môi trường riêng ở đường dẫn ASCII, rồi ghi nhật ký vào pipeline_runs.

    python -m pipeline.spark_job              # CSV -> Bronze -> Silver -> Gold + số liệu đối soát (2-5 phút)
    python -m pipeline.spark_job --ml         # thêm Spark MLlib (GBT, FP-Growth), ~5-10 phút
    python -m pipeline.spark_job --benchmark  # đo hiệu năng theo số lõi và cỡ dữ liệu

Vì sao cần file này: dự án nằm ở thư mục có dấu tiếng Việt, JVM trên Windows treo khi gặp đường dẫn đó. Nên pyspark được cài
ở %LOCALAPPDATA%\\VietJobs\\spark-venv (scripts/setup_spark.py), và mã nguồn + CSV được chép sang thư mục ASCII trước khi chạy.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from app.config import LAKE_DIR, RAW_CSV, ROOT_DIR, SPARK_HOME_DIR, SPARK_PYTHON

from .runlog import finish_run, start_run

WORK = SPARK_HOME_DIR / "work"
LAKE = SPARK_HOME_DIR / "lake"
# Thời hạn (giây), gấp vài lần thời gian chạy bình thường trên máy 4 lõi
TIMEOUT_BATCH, TIMEOUT_BENCHMARK, TIMEOUT_ML = 600, 900, 1800


def available() -> tuple[bool, str]:
    if not SPARK_PYTHON.exists():
        return False, "Chưa cài môi trường Spark. Chạy: python scripts/setup_spark.py"
    if shutil.which("java") is None and not os.getenv("JAVA_HOME"):
        return False, "Không tìm thấy Java (cần JDK 17 trở lên)"
    return True, "Sẵn sàng"


def _prepare() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    LAKE.mkdir(parents=True, exist_ok=True)
    for src, dst in ((ROOT_DIR / "spark" / "spark_pipeline.py", "spark_pipeline.py"),
                     (ROOT_DIR / "spark" / "benchmark.py", "benchmark.py"),
                     (ROOT_DIR / "backend" / "pipeline" / "cleaning.py", "vj_cleaning.py")):
        shutil.copyfile(src, WORK / dst)
    # Python worker chỉ có 10 giây để kết nối lại với JVM. Máy vừa khởi động thì import pandas, pyarrow chậm hơn thế,
    # nên nạp sẵn một lần để hệ điều hành có file trong cache
    print("Khởi động môi trường Python của Spark...", flush=True)
    subprocess.run([str(SPARK_PYTHON), "-c", "import pandas, pyarrow, pyspark"], cwd=WORK, env=_env(), timeout=300,
                   capture_output=True)
    csv = WORK / "VietJobs.csv"
    if not csv.exists() or csv.stat().st_size != RAW_CSV.stat().st_size:
        shutil.copyfile(RAW_CSV, csv)


def _env() -> dict:
    py = str(SPARK_PYTHON)
    env = {**os.environ, "PYSPARK_PYTHON": py, "PYSPARK_DRIVER_PYTHON": py, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    env["PYTHONPATH"] = str(WORK)  # để Python worker import được vj_cleaning
    env.pop("SPARK_HOME", None)
    return env


# Dòng log không có ích cho người xem: cảnh báo khởi động và thông báo dọn tiến trình của Windows
NOISE = ("WARN", "Setting default log level", "sc.setLogLevel", "Using Spark's default log4j", "SUCCESS: The process",
         "ERROR: The process", "Reason: The operation attempted")


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        subprocess.run(["pkill", "-TERM", "-P", str(pid)], capture_output=True)


def _stream(cmd: list[str], timeout: int) -> tuple[int, list[str]]:
    """Chạy Spark, in log theo thời gian thực. Quá thời hạn thì dừng cả cây tiến trình: job treo không được treo theo cả hệ thống."""
    proc = subprocess.Popen(cmd, cwd=WORK, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        _kill_tree(proc.pid)

    timer = threading.Timer(timeout, expire)
    timer.start()
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line and not any(n in line for n in NOISE):
                print(line, flush=True)
                lines.append(line)
        code = proc.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        lines.append(f"Quá thời hạn {timeout} giây, đã dừng Spark")
        print(lines[-1], flush=True)
        return -1, lines
    return code, lines


def run(ml: bool = False, benchmark: bool = False) -> dict:
    ok, reason = available()
    if not ok:
        raise SystemExit(reason)
    job = "benchmark" if benchmark else "spark"
    run_id, t0 = start_run(job), time.time()
    _prepare()
    if benchmark:
        cmd = [str(SPARK_PYTHON), str(WORK / "benchmark.py"), "--silver", str(LAKE / "silver"), "--export", str(LAKE_DIR)]
    else:
        cmd = [str(SPARK_PYTHON), str(WORK / "spark_pipeline.py"), "--csv", str(WORK / "VietJobs.csv"), "--lake", str(LAKE),
               "--export", str(LAKE_DIR), "--cleaning", str(WORK / "vj_cleaning.py")] + (["--ml"] if ml else [])
    timeout = TIMEOUT_ML if ml else TIMEOUT_BENCHMARK if benchmark else TIMEOUT_BATCH
    code, lines = _stream(cmd, timeout)
    if code != 0:
        finish_run(run_id, "failed", time.time() - t0, detail={"error": f"Spark thoát với mã {code}"},
                   log_tail="\n".join(lines[-200:]))
        raise SystemExit(f"Spark thất bại (mã {code})")
    info: dict = {}
    if not benchmark:
        metrics = json.loads((LAKE_DIR / "spark_metrics.json").read_text(encoding="utf-8"))
        info = {"rows_in": metrics["reconcile"]["n_rows"], "rows_out": metrics["reconcile"]["n_jobs"],
                "detail": {"stages": metrics["stages"], "parallelism": metrics["parallelism"]}}
    finish_run(run_id, "success", time.time() - t0, log_tail="\n".join(lines[-200:]), **info)
    return info


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ml", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    a = ap.parse_args()
    run(ml=a.ml, benchmark=a.benchmark)
