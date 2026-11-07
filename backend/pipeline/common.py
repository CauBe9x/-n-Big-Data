"""Tiện ích dùng chung cho các bước huấn luyện: chia tập, ghi kết quả vào PostgreSQL."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sqlalchemy import insert

from app.config import RANDOM_STATE
from app.db import MLModel, ModelMetric, SessionLocal, TrainingRun


def split_80_10_10(df: pd.DataFrame, stratify_col: str | None = None):
    """Chia train/val/test = 80/10/10 giống bài báo VietJobs (LREC 2026)."""
    strat = df[stratify_col] if stratify_col else None
    train, rest = train_test_split(df, test_size=0.2, random_state=RANDOM_STATE, stratify=strat)
    strat_rest = rest[stratify_col] if stratify_col else None
    val, test = train_test_split(rest, test_size=0.5, random_state=RANDOM_STATE, stratify=strat_rest)
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


def _jsonable(o):
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def to_json(obj):
    """Chuyển numpy -> kiểu Python thuần để ghi JSONB."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=_jsonable))


def record_run(task: str, report: dict, results: dict[str, dict], best: str, artifact_path: str | None) -> int:
    """Ghi 1 lần huấn luyện: ml_training_runs -> ml_models -> model_metrics (dạng dài). Trả về run_id.

    results[model] = {"val": {metric: v}, "test": {...}, "test_title_only": {...}, "train_seconds": s, "threshold": t}
    Các khoá là dict -> split; các khoá số còn lại -> split 'info'.
    """
    with SessionLocal() as db:
        run = TrainingRun(task=task, n_train=int(report["n_train"]), n_val=int(report["n_val"]),
                          n_test=int(report["n_test"]), report=to_json(report))
        db.add(run)
        db.flush()
        metric_rows = []
        for name, res in results.items():
            m = MLModel(run_id=run.id, name=name, is_best=(name == best),
                        artifact_path=artifact_path if name == best else None,
                        train_seconds=res.get("train_seconds"))
            db.add(m)
            db.flush()
            for key, val in res.items():
                if isinstance(val, dict):
                    metric_rows += [dict(model_id=m.id, split=key, metric=k, value=float(v)) for k, v in val.items()]
                elif key != "train_seconds" and isinstance(val, (int, float, np.floating)):
                    metric_rows.append(dict(model_id=m.id, split="info", metric=key, value=float(val)))
        if metric_rows:
            db.execute(insert(ModelMetric), metric_rows)
        db.commit()
        return run.id
