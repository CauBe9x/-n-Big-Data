"""API tra cứu tin tuyển dụng + danh mục (meta) cho bộ lọc."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from pipeline.cleaning import EXPERIENCE_BUCKETS, ascii_key
from pipeline.inference import ModelNotReady, predict_salary

from ..db import Category, Job, JobCategory, JobSkill, Language, Province, Skill, get_session

router = APIRouter(prefix="/api", tags=["Tin tuyển dụng"])


@router.get("/meta")
def meta(db: Session = Depends(get_session)):
    cats = db.execute(select(Category.slug, Category.name, func.count(JobCategory.job_id))
                      .join(JobCategory, JobCategory.category_id == Category.id)
                      .group_by(Category.id).order_by(func.count(JobCategory.job_id).desc())).all()
    provs = db.execute(select(Province.name, func.count(Job.id)).join(Job, Job.province_id == Province.id)
                       .group_by(Province.id).order_by(func.count(Job.id).desc())).all()
    contracts = db.execute(select(Job.contract_type, func.count(Job.id)).group_by(Job.contract_type)
                           .order_by(func.count(Job.id).desc())).all()
    skills = db.execute(select(Skill.name, Skill.kind, func.count(JobSkill.job_id)).join(JobSkill, JobSkill.skill_id == Skill.id)
                        .group_by(Skill.id).having(func.count(JobSkill.job_id) >= 5)
                        .order_by(func.count(JobSkill.job_id).desc()).limit(800)).all()
    langs = db.execute(select(Language.name)).scalars().all()
    return {
        "categories": [{"slug": s, "name": n, "count": c} for s, n, c in cats],
        "provinces": [{"name": n, "count": c} for n, c in provs],
        "contract_types": [{"name": n, "count": c} for n, c in contracts],
        "experience_buckets": EXPERIENCE_BUCKETS,
        "skills": [{"name": n, "kind": k, "count": c} for n, k, c in skills],
        "languages": sorted(langs),
    }


def _job_brief(j: Job) -> dict:
    return {"id": j.id, "title": j.title, "category": j.category.name if j.category else None,
            "category_slug": j.category.slug if j.category else None,
            "province": j.province.name if j.province else None, "location": j.location_raw,
            "experience": j.experience_raw, "contract_type": j.contract_type,
            "salary_min": j.salary_min, "salary_max": j.salary_max, "salary_avg": j.salary_avg,
            "is_negotiable": j.is_negotiable, "salary_text": j.salary_raw}


@router.get("/jobs")
def list_jobs(q: str | None = None, category: str | None = None, province: str | None = None,
              experience: str | None = None, contract_type: str | None = None, skill: str | None = None,
              min_salary: float | None = None, max_salary: float | None = None,
              has_salary: bool | None = None, sort: str = Query("relevance", pattern="^(relevance|salary_desc|salary_asc)$"),
              page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_session)):
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(422, "Lương tối thiểu phải nhỏ hơn hoặc bằng lương tối đa")
    stmt = select(Job)
    if q:
        stmt = stmt.where(Job.title_key.like(f"%{ascii_key(q)}%"))
    if category:
        stmt = stmt.where(Job.id.in_(select(JobCategory.job_id).join(Category, Category.id == JobCategory.category_id)
                                     .where(Category.slug == category)))
    if province:
        stmt = stmt.join(Province, Province.id == Job.province_id).where(Province.name == province)
    if experience:
        stmt = stmt.where(Job.experience_bucket == experience)
    if contract_type:
        stmt = stmt.where(Job.contract_type == contract_type)
    if skill:
        stmt = stmt.where(Job.id.in_(select(JobSkill.job_id).join(Skill, Skill.id == JobSkill.skill_id)
                                     .where(Skill.name == skill.lower().strip())))
    if min_salary is not None:
        stmt = stmt.where(Job.salary_avg >= min_salary)
    if max_salary is not None:
        stmt = stmt.where(Job.salary_avg <= max_salary)
    if has_salary is not None:
        stmt = stmt.where(Job.is_negotiable.is_(not has_salary))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if sort == "salary_desc":
        stmt = stmt.order_by(Job.salary_avg.desc().nulls_last(), Job.id)
    elif sort == "salary_asc":
        stmt = stmt.order_by(Job.salary_avg.asc().nulls_last(), Job.id)
    else:
        stmt = stmt.order_by(Job.id)
    rows = db.execute(stmt.options(selectinload(Job.category), selectinload(Job.province))
                      .offset((page - 1) * size).limit(size)).scalars().all()
    return {"total": total, "page": page, "size": size, "items": [_job_brief(j) for j in rows]}


@router.get("/jobs/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_session)):
    j = db.get(Job, job_id, options=[selectinload(Job.skills), selectinload(Job.languages), selectinload(Job.categories),
                                     selectinload(Job.category), selectinload(Job.province)])
    if not j:
        raise HTTPException(404, "Không tìm thấy tin tuyển dụng")
    data = _job_brief(j)
    data.update({
        "country": j.country, "working_hours": j.working_hours, "description": j.description,
        "requirements_text": j.requirements_text, "experience_years": j.experience_years,
        "qualifications": j.qualifications or [], "benefits": j.benefits or [],
        "technical_skills": [s.name for s in j.skills if s.kind == "technical"],
        "soft_skills": [s.name for s in j.skills if s.kind == "soft"],
        "languages": [l.name for l in j.languages],
        "all_categories": [c.name for c in j.categories],
    })
    # Tin "Thoả thuận": dùng mô hình ước tính mức lương tham khảo
    data["estimated_salary"] = None
    if j.is_negotiable:
        try:
            data["estimated_salary"] = predict_salary({
                "title": j.title, "province": data["province"], "experience_years": j.experience_years,
                "contract_type": j.contract_type, "category": data["category_slug"],
                "skills": data["technical_skills"] + data["soft_skills"], "languages": data["languages"]})
        except ModelNotReady:
            pass
    return data
