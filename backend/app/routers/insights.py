"""API khai phá dữ liệu & đánh giá mô hình – đọc từ các bảng kết quả trong PostgreSQL."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from pipeline.cleaning import ascii_key
from pipeline.inference import models_status

from ..db import (AssociationRule, Category, Cluster, ClusterKScore, Job, JobCluster, MiningRun, MLModel, ModelMetric,
                  Skill, SkillSalaryStat, TrainingRun, get_session)

router = APIRouter(prefix="/api", tags=["Khai phá dữ liệu & đánh giá"])


def _latest_run(db: Session, kind: str) -> MiningRun:
    run = db.scalar(select(MiningRun).where(MiningRun.kind == kind).order_by(MiningRun.id.desc()).limit(1))
    if run is None:
        raise HTTPException(503, f"Chưa có kết quả '{kind}'. Hãy chạy: python -m pipeline.run_all --skip-etl")
    return run


# ------------------------------------------------------------------ luật kết hợp
@router.get("/mining/rules")
def rules(type: str | None = Query(None, pattern="^(skill|category|salary)$"), skill: str | None = None,
          consequent: str | None = None, min_lift: float = 1.2, min_confidence: float = 0.0,
          limit: int = Query(50, le=600), db: Session = Depends(get_session)):
    run = _latest_run(db, "association_rules")
    stmt = (select(AssociationRule).where(AssociationRule.run_id == run.id, AssociationRule.lift >= min_lift,
                                          AssociationRule.confidence >= min_confidence)
            .options(selectinload(AssociationRule.antecedents))
            .order_by(AssociationRule.lift.desc(), AssociationRule.confidence.desc()))
    if type:
        stmt = stmt.where(AssociationRule.consequent_type == type)
    rows = db.execute(stmt).scalars().all()
    out = []
    for r in rows:
        ants = sorted(s.name for s in r.antecedents)
        if skill and not any(ascii_key(skill) in ascii_key(a) for a in ants):
            continue
        if consequent and ascii_key(consequent) not in ascii_key(r.consequent_label):
            continue
        out.append({"rule_id": r.id, "antecedents": ants, "consequent": r.consequent_label,
                    "consequent_type": r.consequent_type, "support": r.support, "confidence": r.confidence,
                    "lift": r.lift})
    total = db.scalar(select(func.count()).select_from(AssociationRule).where(AssociationRule.run_id == run.id))
    return {**run.params, "n_rules_total": total, "count": len(out), "rules": out[:limit]}


# ------------------------------------------------------------------ phân cụm
@router.get("/mining/clusters")
def clusters(db: Session = Depends(get_session)):
    run = _latest_run(db, "clustering")
    cl = db.execute(select(Cluster).where(Cluster.run_id == run.id).order_by(Cluster.size.desc())).scalars().all()
    scores = db.execute(select(ClusterKScore).where(ClusterKScore.run_id == run.id).order_by(ClusterKScore.k)).scalars()
    pts = db.execute(select(JobCluster.pca_x, JobCluster.pca_y, JobCluster.cluster_id, Job.title)
                     .join(Job, Job.id == JobCluster.job_id).join(Cluster, Cluster.id == JobCluster.cluster_id)
                     .where(Cluster.run_id == run.id, JobCluster.pca_x.is_not(None))).all()
    return {
        "k": run.params["k"], "explained_variance_svd": run.params.get("explained_variance_svd"),
        "silhouette": {s.k: s.silhouette for s in scores},
        "clusters": [{"id": c.id, "label": c.label, "size": c.size, "median_salary": c.median_salary,
                      "top_terms": c.top_terms, "top_skills": c.top_skills, "distinct_skills": c.distinct_skills,
                      "top_soft_skills": c.top_soft_skills, "example_titles": c.example_titles,
                      "top_categories": c.top_categories} for c in cl],
        "points": [{"x": round(x, 4), "y": round(y, 4), "c": cid, "t": t[:60]} for x, y, cid, t in pts],
    }


@router.get("/mining/clusters/{cluster_id}/jobs")
def cluster_jobs(cluster_id: int, limit: int = Query(20, le=100), db: Session = Depends(get_session)):
    rows = db.execute(select(Job.id, Job.title, Job.salary_avg).join(JobCluster, JobCluster.job_id == Job.id)
                      .where(JobCluster.cluster_id == cluster_id).order_by(Job.salary_avg.desc().nulls_last())
                      .limit(limit)).all()
    return [{"id": i, "title": t, "salary_avg": s} for i, t, s in rows]


# ------------------------------------------------------------------ kỹ năng & lương
@router.get("/mining/skill-value")
def skill_value(kind: str | None = Query(None, pattern="^(technical|soft)$"),
                sort: str = Query("n_jobs", pattern="^(n_jobs|median_salary|premium)$"),
                min_jobs: int = 30, limit: int = Query(30, le=500), db: Session = Depends(get_session)):
    run = _latest_run(db, "skill_salary")
    order = {"n_jobs": SkillSalaryStat.n_jobs, "median_salary": SkillSalaryStat.median_salary,
             "premium": SkillSalaryStat.premium_pct}[sort]
    stmt = (select(SkillSalaryStat, Skill.name, Skill.kind, Category.name)
            .join(Skill, Skill.id == SkillSalaryStat.skill_id)
            .outerjoin(Category, Category.id == SkillSalaryStat.top_category_id)
            .where(SkillSalaryStat.run_id == run.id, SkillSalaryStat.n_with_salary >= min_jobs)
            .order_by(order.desc()).limit(limit))
    if kind:
        stmt = stmt.where(Skill.kind == kind)
    return [{"skill": name, "kind": k, "n_jobs": s.n_jobs, "n_with_salary": s.n_with_salary,
             "median_salary": s.median_salary, "mean_salary": s.mean_salary, "premium_%": s.premium_pct,
             "top_category": cat} for s, name, k, cat in db.execute(stmt).all()]


# ------------------------------------------------------------------ đánh giá mô hình
@router.get("/models/reports")
def model_reports(db: Session = Depends(get_session)):
    """Lần huấn luyện mới nhất của mỗi bài toán: chỉ số (bảng model_metrics) + báo cáo chi tiết (JSONB)."""
    out = {"status": models_status()}
    for task in ("salary", "skills", "category"):
        run = db.scalar(select(TrainingRun).where(TrainingRun.task == task).order_by(TrainingRun.id.desc()).limit(1))
        if run is None:
            out[task] = None
            continue
        models = db.execute(select(MLModel).where(MLModel.run_id == run.id).order_by(MLModel.id)
                            .options(selectinload(MLModel.metrics))).scalars().all()
        results = {}
        for m in models:
            res: dict = {"train_seconds": m.train_seconds}
            for mm in m.metrics:
                if mm.split == "info":
                    res[mm.metric] = mm.value
                else:
                    res.setdefault(mm.split, {})[mm.metric] = mm.value
            results[m.name] = res
        best = next((m.name for m in models if m.is_best), None)
        out[task] = {**run.report, "results": results, "best_model": best, "run_id": run.id,
                     "trained_at": run.trained_at.isoformat()}
    return out
