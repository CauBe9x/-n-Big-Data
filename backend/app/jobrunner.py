"""Chạy các job pipeline an toàn từ giao diện: mỗi lần một job, tiến trình con, log đọc được theo thời gian thực.

Chỉ cho phép các job trong JOBS (không nhận lệnh tuỳ ý). ETL và huấn luyện không có ở đây: ETL tạo lại toàn bộ lược đồ và
huấn luyện mất ~20 phút, nên chỉ chạy bằng dòng lệnh.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from .config import BACKEND_DIR

JOBS = {
    "quality": {"label": "Kiểm định chất lượng dữ liệu", "args": ["-m", "pipeline.quality"], "estimate": "khoảng 20 giây"},
    "spark": {"label": "Spark batch: CSV → Bronze → Silver → Gold", "args": ["-m", "pipeline.spark_job"],
              "estimate": "2–5 phút", "needs_spark": True},
}


@dataclass
class ActiveJob:
    job: str
    started: float = field(default_factory=time.time)
    finished: float | None = None
    exit_code: int | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=300))

    def as_dict(self) -> dict:
        end = self.finished or time.time()
        return {"job": self.job, "label": JOBS[self.job]["label"], "running": self.finished is None,
                "exit_code": self.exit_code, "seconds": round(end - self.started, 1), "log": list(self.log)}


class JobRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self.current: ActiveJob | None = None

    @property
    def busy(self) -> bool:
        return self.current is not None and self.current.finished is None

    def start(self, job: str) -> ActiveJob:
        with self._lock:
            if self.busy:
                raise RuntimeError(f"Đang chạy: {JOBS[self.current.job]['label']}")
            self.current = ActiveJob(job)
            active = self.current
        threading.Thread(target=self._run, args=(active,), daemon=True).start()
        return active

    def _run(self, active: ActiveJob) -> None:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "VIETJOBS_TRIGGER": "ui"}
        try:
            proc = subprocess.Popen([sys.executable, *JOBS[active.job]["args"]], cwd=BACKEND_DIR, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                if line.strip():
                    active.log.append(line.rstrip())
            active.exit_code = proc.wait()
        except Exception as exc:  # noqa: BLE001
            active.log.append(f"Không chạy được job: {exc}")
            active.exit_code = -1
        active.finished = time.time()


runner = JobRunner()
