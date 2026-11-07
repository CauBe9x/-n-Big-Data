"""Suy luận + giải thích cho 3 mô hình (backend gọi các hàm ở đây)."""
from __future__ import annotations

import math
from functools import lru_cache

import joblib
import numpy as np
from scipy import sparse

from app.config import ARTIFACTS_DIR

from .features import FEATURE_GROUP_LABELS, salary_frame, text_frame


class ModelNotReady(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    path = ARTIFACTS_DIR / name
    if not path.exists():
        raise ModelNotReady(f"Chưa có mô hình {name}. Hãy chạy: python -m pipeline.run_all")
    return joblib.load(path)


def reload_models() -> None:
    _load.cache_clear()


def models_status() -> dict:
    return {n: (ARTIFACTS_DIR / f"{n}_model.joblib").exists() for n in ("salary", "skills", "category")}


# ---------------------------------------------------------------------------
# Lương
# ---------------------------------------------------------------------------

def _pretty_feature(name: str) -> str:
    group, _, value = name.partition("__")
    label = FEATURE_GROUP_LABELS.get(group, group)
    for prefix in ("province_", "contract_type_", "category_", "exp_bucket_"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    if group == "category":
        value = value.replace("_", " ")
    if group == "exp_years":
        return "Số năm kinh nghiệm"
    return f"{label}: “{value}”"


def _explain(bundle: dict, frame) -> tuple[float, list[dict], list[dict]]:
    pipe = bundle["model"]
    prep, model = pipe.named_steps["prep"], pipe.named_steps["model"]
    Xt = prep.transform(frame)
    names = prep.get_feature_names_out()
    row = Xt[0].toarray().ravel() if sparse.issparse(Xt) else np.asarray(Xt[0]).ravel()

    if hasattr(model, "coef_"):  # mô hình tuyến tính: đóng góp = w * (x - mean)
        means = bundle.get("feature_means")
        means = np.zeros_like(row) if means is None else means
        contrib = model.coef_ * (row - means)
        base = float(model.intercept_ + model.coef_ @ means)
    else:  # LightGBM: giá trị SHAP (pred_contrib)
        c = model.predict(Xt[:1], pred_contrib=True)
        c = np.asarray(c.toarray() if sparse.issparse(c) else c).ravel()
        contrib, base = c[:-1], float(c[-1])

    groups: dict[str, float] = {}
    for n, v in zip(names, contrib):
        g = FEATURE_GROUP_LABELS.get(n.split("__")[0], n.split("__")[0])
        if g.startswith("Chức danh"):
            g = "Chức danh"
        groups[g] = groups.get(g, 0.0) + float(v)
    group_list = sorted(({"factor": g, "effect_pct": (math.exp(v) - 1) * 100} for g, v in groups.items()),
                        key=lambda d: -abs(d["effect_pct"]))

    # n-gram ký tự khó đọc với người dùng -> chỉ liệt kê các đặc trưng dễ hiểu
    present = [i for i in np.flatnonzero(row != 0) if not names[i].startswith("title_char__")]
    top = [i for i in sorted(present, key=lambda i: -abs(contrib[i])) if abs(contrib[i]) >= 0.005][:8]  # bỏ tác động < 0,5%
    feats = [{"feature": _pretty_feature(names[i]), "effect_pct": (math.exp(contrib[i]) - 1) * 100} for i in top]
    return base, group_list, feats


def predict_salary(payload: dict) -> dict:
    bundle = _load("salary_model.joblib")
    frame = salary_frame([payload])
    log_pred = float(bundle["model"].predict(frame)[0])
    pred = math.expm1(log_pred)
    lo = math.expm1(log_pred + bundle.get("log_resid_q10", -0.25))
    hi = math.expm1(log_pred + bundle.get("log_resid_q90", 0.25))
    try:
        base, groups, feats = _explain(bundle, frame)
        base_salary = math.expm1(base)
    except Exception:  # giải thích là phần phụ, không làm hỏng dự đoán
        base_salary, groups, feats = None, [], []
    return {"model": bundle["name"], "predicted": round(pred, 1), "low": round(lo, 1), "high": round(hi, 1),
            "unit": "triệu VNĐ/tháng", "baseline_salary": None if base_salary is None else round(base_salary, 1),
            "factors": groups, "top_features": feats}


# ---------------------------------------------------------------------------
# Kỹ năng
# ---------------------------------------------------------------------------

def predict_skills(title: str, description: str | None = None, top_k: int = 15) -> dict:
    bundle = _load("skills_model.joblib")
    proba = bundle["model"].predict_proba(text_frame([title], [description or ""]))[0]
    order = np.argsort(-proba)
    thr = bundle["threshold"]
    out = {"technical": [], "soft": []}
    for j in order:
        kind, name = bundle["labels"][j].split("::", 1)
        key = "technical" if kind == "T" else "soft"
        limit = top_k if key == "technical" else max(5, top_k // 2)
        if len(out[key]) < limit:
            out[key].append({"skill": name, "probability": round(float(proba[j]), 4), "recommended": bool(proba[j] >= thr)})
        if len(out["technical"]) >= top_k and len(out["soft"]) >= max(5, top_k // 2):
            break
    return {"model": bundle["name"], "threshold": thr, **out}


# ---------------------------------------------------------------------------
# Ngành nghề
# ---------------------------------------------------------------------------

def _softmax(z):
    z = np.asarray(z, dtype=float)
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def predict_category(title: str, description: str | None = None, top_k: int = 5) -> dict:
    bundle = _load("category_model.joblib")
    pipe = bundle["model"]
    X = text_frame([title], [description or ""])
    clf = pipe.named_steps["clf"]
    if hasattr(clf, "predict_proba"):
        scores = pipe.predict_proba(X)[0]
    else:  # Linear SVM -> softmax của decision_function (điểm tương đối)
        scores = _softmax(pipe.decision_function(X)[0] * 3)
    classes = list(clf.classes_)
    order = np.argsort(-scores)[:top_k]
    return {"model": bundle["name"],
            "predictions": [{"slug": str(classes[i]), "category": str(bundle["names"].get(classes[i], classes[i])),
                             "score": round(float(scores[i]), 4)} for i in order]}
