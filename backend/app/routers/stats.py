"""API thống kê / EDA – truy vấn trực tiếp CSDL bằng SQL (GROUP BY, JOIN)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import Category, Job, JobCategory, JobLanguage, JobSkill, Language, Province, Skill, get_session

router = APIRouter(prefix="/api/stats", tags=["Thống kê"])

SAL_LO, SAL_HI = 1, 150
EXP_ORDER = ["Không yêu cầu", "Dưới 1 năm", "1-2 năm", "3-5 năm", "Trên 5 năm", "Không rõ"]


def _filters(stmt, category: str | None, province: str | None):
    if category:
        # một tin có thể thuộc nhiều ngành -> lọc qua bảng nối job_categories
        stmt = stmt.where(Job.id.in_(select(JobCategory.job_id).join(Category, Category.id == JobCategory.category_id)
                                     .where(Category.slug == category)))
    if province:
        stmt = stmt.where(Job.province_id == select(Province.id).where(Province.name == province).scalar_subquery())
    return stmt


def _salary_frame(db: Session, key_col, category=None, province=None) -> pd.DataFrame:
    stmt = select(key_col.label("key"), Job.salary_avg).where(Job.salary_avg.between(SAL_LO, SAL_HI))
    if key_col.class_ is Category:
        stmt = (stmt.join(JobCategory, JobCategory.job_id == Job.id)
                .join(Category, Category.id == JobCategory.category_id))
    elif key_col.class_ is Province:
        stmt = stmt.join(Province, Province.id == Job.province_id)
    stmt = _filters(stmt, category, province)
    return pd.DataFrame(db.execute(stmt).all(), columns=["key", "salary"])


def _summ(s: pd.Series) -> dict:
    return {"median_salary": round(float(s.median()), 1), "mean_salary": round(float(s.mean()), 1),
            "p25": round(float(s.quantile(0.25)), 1), "p75": round(float(s.quantile(0.75)), 1)}


@router.get("/overview")
def overview(category: str | None = None, province: str | None = None, db: Session = Depends(get_session)):
    base = _filters(select(func.count(Job.id)), category, province)
    total = db.scalar(base) or 0
    negotiable = db.scalar(base.where(Job.is_negotiable.is_(True))) or 0
    sal = [r[0] for r in db.execute(_filters(select(Job.salary_avg).where(Job.salary_avg.between(SAL_LO, SAL_HI)),
                                             category, province)).all()]
    s = pd.Series(sal, dtype=float)
    return {
        "total_jobs": total,
        "with_salary": total - negotiable,
        "negotiable_pct": round(negotiable * 100 / total, 1) if total else 0,
        **(_summ(s) if len(s) else {}),
        "n_categories": db.scalar(select(func.count(Category.id))),
        "n_provinces": db.scalar(select(func.count(Province.id))),
        "n_skills": db.scalar(select(func.count(Skill.id))),
        "n_skill_links": db.scalar(select(func.count()).select_from(JobSkill)),
    }


@router.get("/categories")
def by_category(province: str | None = None, db: Session = Depends(get_session)):
    stmt = (select(Category.slug, Category.name, func.count(Job.id),
                   func.sum(case((Job.is_negotiable.is_(True), 1), else_=0)))
            .join(JobCategory, JobCategory.category_id == Category.id)
            .join(Job, Job.id == JobCategory.job_id).group_by(Category.id))
    stmt = _filters(stmt, None, province)
    counts = {slug: (name, n, neg or 0) for slug, name, n, neg in db.execute(stmt).all()}
    df = _salary_frame(db, Category.slug, province=province)
    out = []
    for slug, (name, n, neg) in counts.items():
        s = df.loc[df.key == slug, "salary"]
        out.append({"slug": slug, "name": name, "count": n, "negotiable_pct": round(neg * 100 / n, 1),
                    **(_summ(s) if len(s) else {})})
    return sorted(out, key=lambda r: -r["count"])


@router.get("/provinces")
def by_province(limit: int = Query(15, le=70), category: str | None = None, db: Session = Depends(get_session)):
    stmt = _filters(select(Province.name, func.count(Job.id)).join(Job, Job.province_id == Province.id)
                    .group_by(Province.id).order_by(func.count(Job.id).desc()), category, None)
    rows = db.execute(stmt.limit(limit)).all()
    df = _salary_frame(db, Province.name, category=category)
    out = []
    for name, n in rows:
        s = df.loc[df.key == name, "salary"]
        out.append({"province": name, "count": n, **(_summ(s) if len(s) >= 5 else {})})
    return out


@router.get("/experience")
def by_experience(category: str | None = None, province: str | None = None, db: Session = Depends(get_session)):
    df = _salary_frame(db, Job.experience_bucket, category, province)
    cnt = dict(db.execute(_filters(select(Job.experience_bucket, func.count(Job.id)).group_by(Job.experience_bucket),
                                   category, province)).all())
    out = []
    for b in EXP_ORDER:
        s = df.loc[df.key == b, "salary"]
        if cnt.get(b):
            out.append({"bucket": b, "count": cnt[b], **(_summ(s) if len(s) else {})})
    return out


@router.get("/salary-distribution")
def salary_distribution(category: str | None = None, province: str | None = None, bin_size: int = 5,
                        max_value: int = 100, db: Session = Depends(get_session)):
    sal = np.array([r[0] for r in db.execute(_filters(select(Job.salary_avg).where(Job.salary_avg.between(SAL_LO, SAL_HI)),
                                                      category, province)).all()], dtype=float)
    edges = list(range(0, max_value + bin_size, bin_size))
    hist, _ = np.histogram(np.clip(sal, 0, max_value - 0.01), bins=edges)
    return [{"range": f"{a}-{b}" if b < max_value else f"{a}+", "from": a, "to": b, "count": int(c)}
            for a, b, c in zip(edges[:-1], edges[1:], hist)]


@router.get("/top-skills")
def top_skills(kind: str = Query("technical", pattern="^(technical|soft)$"), limit: int = Query(20, le=100),
               category: str | None = None, province: str | None = None, db: Session = Depends(get_session)):
    stmt = (select(Skill.name, func.count(JobSkill.job_id).label("n"))
            .join(JobSkill, JobSkill.skill_id == Skill.id).join(Job, Job.id == JobSkill.job_id)
            .where(Skill.kind == kind).group_by(Skill.id).order_by(func.count(JobSkill.job_id).desc()).limit(limit))
    stmt = _filters(stmt, category, province)
    total = db.scalar(_filters(select(func.count(Job.id)), category, province)) or 1
    return [{"skill": n, "count": c, "share_pct": round(c * 100 / total, 2)} for n, c in db.execute(stmt).all()]


@router.get("/contract-types")
def contract_types(category: str | None = None, db: Session = Depends(get_session)):
    stmt = _filters(select(Job.contract_type, func.count(Job.id), func.avg(Job.salary_avg))
                    .group_by(Job.contract_type).order_by(func.count(Job.id).desc()), category, None)
    return [{"contract_type": c, "count": n, "mean_salary": round(a, 1) if a else None} for c, n, a in db.execute(stmt).all()]


@router.get("/languages")
def languages(db: Session = Depends(get_session)):
    """Ảnh hưởng của yêu cầu ngoại ngữ tới lương."""
    rows = db.execute(select(Language.name, Job.salary_avg).join(JobLanguage, JobLanguage.language_id == Language.id)
                      .join(Job, Job.id == JobLanguage.job_id)).all()
    df = pd.DataFrame(rows, columns=["lang", "salary"])
    no_lang = [r[0] for r in db.execute(select(Job.salary_avg).where(
        Job.salary_avg.between(SAL_LO, SAL_HI), ~Job.id.in_(select(JobLanguage.job_id)))).all()]
    out = [{"language": "Không yêu cầu ngoại ngữ", "count": len(no_lang),
            "median_salary": round(float(np.median(no_lang)), 1) if no_lang else None}]
    for lang, g in df.groupby("lang"):
        s = g["salary"].dropna()
        s = s[(s >= SAL_LO) & (s <= SAL_HI)]
        if len(g) >= 20:
            out.append({"language": lang, "count": len(g), "median_salary": round(float(s.median()), 1) if len(s) else None})
    return sorted(out, key=lambda r: -r["count"])
