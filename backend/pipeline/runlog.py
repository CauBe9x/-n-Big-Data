"""Ghi nhật ký chạy từng bước pipeline vào bảng pipeline_runs (số dòng vào/ra, thời gian, trạng thái)."""
from __future__ import annotations

import functools
import os
import time
from datetime import datetime

from app.db import PipelineRun, SessionLocal, ensure_ops_schema

from .common import to_json


def start_run(job: str, trigger: str | None = None) -> int:
    ensure_ops_schema()
    with SessionLocal() as db:
        run = PipelineRun(job=job, trigger=trigger or os.getenv("VIETJOBS_TRIGGER", "cli"))
        db.add(run)
        db.commit()
        return run.id


def finish_run(run_id: int, status: str, seconds: float, rows_in: int | None = None, rows_out: int | None = None,
               detail: dict | None = None, log_tail: str | None = None) -> None:
    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        run.status, run.seconds, run.finished_at = status, round(seconds, 1), datetime.now()
        run.rows_in, run.rows_out = rows_in, rows_out
        if detail is not None:
            run.detail = to_json(detail)
        if log_tail is not None:
            run.log_tail = log_tail[-20000:]
        db.commit()


def tracked(job: str, summarize=None):
    """Bọc một bước pipeline. summarize(kết_quả) -> dict(rows_in, rows_out, detail) cho nhật ký."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            run_id, t0 = start_run(job), time.time()
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                finish_run(run_id, "failed", time.time() - t0, detail={"error": str(exc)[:500]})
                raise
            info = summarize(result) if summarize else {}
            finish_run(run_id, "success", time.time() - t0, **info)
            return result
        return inner
    return wrap
