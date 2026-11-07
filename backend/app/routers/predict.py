"""API dự đoán bằng các mô hình máy học đã huấn luyện."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline import inference as I

from pipeline.common import to_json

from ..db import MLModel, Prediction, TrainingRun, get_session
from ..schemas import SalaryInput, TextInput

router = APIRouter(prefix="/api/predict", tags=["Dự đoán (Machine Learning)"])


def _best_model_id(db: Session, task: str) -> int | None:
    """model_id của mô hình đang triển khai (is_best) trong lần huấn luyện mới nhất."""
    return db.scalar(select(MLModel.id).join(TrainingRun, TrainingRun.id == MLModel.run_id)
                     .where(TrainingRun.task == task, MLModel.is_best.is_(True))
                     .order_by(TrainingRun.id.desc()).limit(1))


def _log(db: Session, task: str, inp: dict, out: dict) -> None:
    """Lưu lượt dự đoán vào bảng predictions (khoá ngoại tới ml_models)."""
    db.add(Prediction(model_id=_best_model_id(db, task), task=task, input=to_json(inp), output=to_json(out)))
    db.commit()


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except I.ModelNotReady as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/salary")
def salary(inp: SalaryInput, db: Session = Depends(get_session)):
    payload = inp.model_dump()
    auto_category = None
    if not payload.get("category"):
        cat = _guard(I.predict_category, payload["title"])["predictions"][0]
        payload["category"] = cat["slug"]
        auto_category = cat
    out = _guard(I.predict_salary, payload)
    out["auto_category"] = auto_category
    _log(db, "salary", payload, {"predicted": out["predicted"], "low": out["low"], "high": out["high"]})
    return out


@router.post("/skills")
def skills(inp: TextInput, db: Session = Depends(get_session)):
    out = _guard(I.predict_skills, inp.title, inp.description, inp.top_k)
    _log(db, "skills", inp.model_dump(), {"technical": [s["skill"] for s in out["technical"][:10]]})
    return out


@router.post("/category")
def category(inp: TextInput, db: Session = Depends(get_session)):
    out = _guard(I.predict_category, inp.title, inp.description, min(inp.top_k, 16))
    _log(db, "category", inp.model_dump(), {"top": out["predictions"][0]["category"]})
    return out


@router.get("/history")
def history(task: str | None = None, limit: int = Query(20, le=200), db: Session = Depends(get_session)):
    stmt = (select(Prediction, MLModel.name).outerjoin(MLModel, MLModel.id == Prediction.model_id)
            .order_by(Prediction.id.desc()).limit(limit))
    if task:
        stmt = stmt.where(Prediction.task == task)
    return [{"id": r.id, "task": r.task, "model": name, "input": r.input, "output": r.output,
             "created_at": r.created_at.isoformat()} for r, name in db.execute(stmt).all()]
