"""API vận hành pipeline: sơ đồ các bước với số liệu thật, nhật ký chạy, chất lượng dữ liệu, đối soát, chạy job."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from pipeline import reconcile as R
from pipeline import spark_job

from ..config import LAKE_DIR
from ..db import AssociationRule, Cluster, Job, JobSkill, MLModel, PipelineRun, Skill, get_session
from ..jobrunner import JOBS, runner

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline Big Data"])

# Thứ tự các bước trong sơ đồ. Mỗi bước gắn với job ghi nhật ký tương ứng.
STEPS = [
    {"job": "etl", "name": "ETL pandas", "tech": "pandas, SQLAlchemy", "output": "PostgreSQL: bảng chuẩn hoá"},
    {"job": "quality", "name": "Kiểm định chất lượng", "tech": "pandas", "output": "Hồ sơ dữ liệu trong pipeline_runs"},
    {"job": "salary", "name": "Huấn luyện mô hình lương", "tech": "LightGBM, Ridge", "output": "salary_model.joblib"},
    {"job": "skills", "name": "Huấn luyện gợi ý kỹ năng", "tech": "OvR Logistic Regression", "output": "skills_model.joblib"},
    {"job": "category", "name": "Huấn luyện phân loại ngành", "tech": "Linear SVM", "output": "category_model.joblib"},
    {"job": "mining", "name": "Khai phá dữ liệu", "tech": "FP-Growth, K-Means", "output": "Luật kết hợp, cụm công việc"},
    {"job": "spark", "name": "Lakehouse Spark", "tech": "PySpark, Parquet", "output": "Bronze, Silver, Gold"},
]


def _run_dict(r: PipelineRun, with_detail: bool = False) -> dict:
    d = {"id": r.id, "job": r.job, "status": r.status, "trigger": r.trigger, "seconds": r.seconds, "rows_in": r.rows_in,
         "rows_out": r.rows_out, "started_at": r.started_at.isoformat(timespec="seconds"),
         "finished_at": r.finished_at.isoformat(timespec="seconds") if r.finished_at else None}
    if with_detail:
        d["detail"], d["log_tail"] = r.detail, r.log_tail
    return d


def _latest(db: Session, job: str) -> PipelineRun | None:
    return db.scalar(select(PipelineRun).where(PipelineRun.job == job, PipelineRun.status == "success")
                     .order_by(PipelineRun.id.desc()).limit(1))


def _json(name: str) -> dict | None:
    path = LAKE_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@router.get("/overview")
def overview(db: Session = Depends(get_session)):
    steps = []
    for s in STEPS:
        last = _latest(db, s["job"])
        steps.append({**s, "last_run": _run_dict(last) if last else None})
    spark_ok, spark_reason = spark_job.available()
    counts = {
        "jobs": db.scalar(select(func.count(Job.id))),
        "skills": db.scalar(select(func.count(Skill.id))),
        "skill_links": db.scalar(select(func.count()).select_from(JobSkill)),
        "rules": db.scalar(select(func.count(AssociationRule.id))),
        "clusters": db.scalar(select(func.count(Cluster.id))),
        "models": db.scalar(select(func.count(MLModel.id))),
    }
    size = db.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    return {"steps": steps, "counts": counts, "database_size": size,
            "jobs_available": [{"job": k, "label": v["label"], "estimate": v["estimate"],
                                "enabled": spark_ok if v.get("needs_spark") else True,
                                "reason": spark_reason if v.get("needs_spark") and not spark_ok else None}
                               for k, v in JOBS.items()],
            "active": runner.current.as_dict() if runner.busy else None}


@router.get("/runs")
def runs(job: str | None = Query(None, max_length=30), limit: int = Query(25, ge=1, le=200),
         db: Session = Depends(get_session)):
    stmt = select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit)
    if job:
        stmt = stmt.where(PipelineRun.job == job)
    return [_run_dict(r) for r in db.scalars(stmt).all()]


@router.get("/quality")
def quality(db: Session = Depends(get_session)):
    last = _latest(db, "quality")
    if last is None:
        raise HTTPException(503, "Chưa có báo cáo chất lượng. Hãy chạy: python -m pipeline.quality")
    return {**last.detail, "run": _run_dict(last)}


@router.get("/spark")
def spark():
    """Kết quả lần chạy Spark gần nhất; các bảng Gold là số liệu do Spark tính, không phải từ PostgreSQL."""
    metrics = _json("spark_metrics.json")
    ok, reason = spark_job.available()
    gold = {}
    gold_dir = LAKE_DIR / "gold"
    if gold_dir.exists():
        for f in sorted(gold_dir.glob("*.json")):
            gold[f.stem] = json.loads(f.read_text(encoding="utf-8"))[:20]
    return {"available": ok, "reason": reason, "metrics": metrics, "gold": gold, "benchmark": _json("benchmark.json")}


@router.post("/reconcile")
def reconcile(db: Session = Depends(get_session)):
    """Chạy lại toàn bộ kiểm tra đối soát ngay bây giờ, trên dữ liệu hiện tại."""
    return R.run_checks(db)


class JobRequest(BaseModel):
    job: Literal["quality", "spark"]


@router.post("/jobs", status_code=202)
def start_job(req: JobRequest):
    if JOBS[req.job].get("needs_spark"):
        ok, reason = spark_job.available()
        if not ok:
            raise HTTPException(409, reason)
    try:
        return runner.start(req.job).as_dict()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/jobs/current")
def current_job():
    return runner.current.as_dict() if runner.current else None
