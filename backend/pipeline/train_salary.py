"""Bài toán 1 – Dự đoán mức lương (hồi quy).

Đầu vào: chức danh, địa điểm, kinh nghiệm, loại hợp đồng, ngành, kỹ năng, ngoại ngữ.
Mục tiêu: salary_avg (triệu VNĐ/tháng), học trên thang log1p để giảm lệch phải.
So sánh: Baseline (trung vị theo ngành) · Ridge · LightGBM. Khoảng lương 80% được ước lượng bằng
split-conformal (phân vị sai số trên tập validation).

Chạy: python -m pipeline.train_salary
"""
from __future__ import annotations

import time

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from app.config import ARTIFACTS_DIR, RANDOM_STATE

from .common import record_run, split_80_10_10
from .etl import load_clean
from .runlog import tracked
from .features import PAPER_SALARY_BLOCKS, salary_frame, salary_preprocessor

SAL_MIN, SAL_MAX = 1.0, 150.0  # triệu/tháng – loại ngoại lai cực đoan

try:
    from lightgbm import LGBMRegressor
except ImportError:  # pragma: no cover
    LGBMRegressor = None


def _metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return {
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "R2": float(r2_score(y_true, y_pred)),
        "MAPE_%": float(np.mean(np.abs(y_true - y_pred) / np.maximum(y_true, 1)) * 100),
        "within_20%": float(np.mean(np.abs(y_true - y_pred) <= 0.2 * y_true) * 100),
    }


class CategoryMedianBaseline:
    """Dự đoán = trung vị lương của ngành trong tập train."""

    def fit(self, X: pd.DataFrame, y):
        s = pd.Series(np.asarray(y), index=X.index)
        self.medians_ = s.groupby(X["category"]).median().to_dict()
        self.global_ = float(np.median(y))
        return self

    def predict(self, X: pd.DataFrame):
        return np.array([self.medians_.get(c, self.global_) for c in X["category"]])


def _lgbm(**kw):
    params = dict(n_estimators=900, learning_rate=0.04, num_leaves=63, min_child_samples=20,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.5, reg_lambda=1.0,
                  random_state=RANDOM_STATE, verbose=-1, n_jobs=-1)
    params.update(kw)
    return LGBMRegressor(**params)


def _summary(r: dict) -> dict:
    return {"rows_in": r["n_train"] + r["n_val"] + r["n_test"], "rows_out": r["n_test"],
            "detail": {"best_model": r["best_model"]}}


@tracked("salary", _summary)
def run() -> dict:
    t0 = time.time()
    df = load_clean()
    data = df[df["sal_avg"].notna()].copy()
    n_all = len(data)
    data = data[(data["sal_avg"] >= SAL_MIN) & (data["sal_avg"] <= SAL_MAX)]
    print(f"[Lương] {n_all} tin có lương; giữ {len(data)} tin trong [{SAL_MIN}, {SAL_MAX}] triệu")

    train, val, test = split_80_10_10(data)
    Xtr, Xva, Xte = (salary_frame(d) for d in (train, val, test))
    ytr, yva, yte = (d["sal_avg"].to_numpy() for d in (train, val, test))
    ltr = np.log1p(ytr)

    candidates: dict[str, object] = {
        "Baseline (trung vị theo ngành)": CategoryMedianBaseline(),
    }
    for alpha in (1.0, 3.0):
        candidates[f"Ridge (alpha={alpha})"] = Pipeline([("prep", salary_preprocessor()), ("model", Ridge(alpha=alpha))])
    if LGBMRegressor is not None:
        candidates["LightGBM"] = Pipeline([("prep", salary_preprocessor()), ("model", _lgbm())])

    results, fitted = {}, {}
    for name, model in candidates.items():
        t = time.time()
        if isinstance(model, CategoryMedianBaseline):
            model.fit(Xtr, ytr)
            pva, pte = model.predict(Xva), model.predict(Xte)
        else:
            model.fit(Xtr, ltr)
            pva, pte = np.expm1(model.predict(Xva)), np.expm1(model.predict(Xte))
        results[name] = {"val": _metrics(yva, pva), "test": _metrics(yte, pte), "train_seconds": round(time.time() - t, 1)}
        fitted[name] = model
        print(f"  - {name:32s} val RMSE={results[name]['val']['RMSE']:.2f}  test RMSE={results[name]['test']['RMSE']:.2f}"
              f"  R2={results[name]['test']['R2']:.3f}  ({results[name]['train_seconds']}s)")

    trainable = {k: v for k, v in results.items() if not k.startswith("Baseline")}
    best = min(trainable, key=lambda k: trainable[k]["val"]["RMSE"])
    best_model = fitted[best]
    print(f"  => Mô hình tốt nhất (theo val RMSE): {best}")

    # Khoảng lương 80% (split-conformal): lấy phân vị P10/P90 của sai số log trên tập val
    log_resid = np.log1p(yva) - best_model.predict(Xva)
    q_lo, q_hi = (float(np.quantile(log_resid, q)) for q in (0.1, 0.9))
    lte = best_model.predict(Xte)
    lo, hi = np.expm1(lte + q_lo), np.expm1(lte + q_hi)
    coverage = float(np.mean((yte >= lo) & (yte <= hi)) * 100)
    results[best]["interval_80_coverage_%"] = coverage
    print(f"  - Khoảng dự đoán 80% bao phủ {coverage:.1f}% giá trị thật trên tập test")

    # Biến thể chỉ dùng các trường như bài báo (chức danh, hợp đồng, địa điểm, kinh nghiệm)
    if LGBMRegressor is not None:
        t = time.time()
        paper = Pipeline([("prep", salary_preprocessor(PAPER_SALARY_BLOCKS)), ("model", _lgbm())]).fit(Xtr, ltr)
        name = "LightGBM – chỉ trường như bài báo"
        results[name] = {"val": _metrics(yva, np.expm1(paper.predict(Xva))),
                         "test": _metrics(yte, np.expm1(paper.predict(Xte))), "train_seconds": round(time.time() - t, 1)}
        print(f"  - {name:32s} test RMSE={results[name]['test']['RMSE']:.2f}  R2={results[name]['test']['R2']:.3f}")

    # Lỗi theo ngành (tập test) – phục vụ phân tích
    pte_best = np.expm1(best_model.predict(Xte))
    err_by_cat = (pd.DataFrame({"cat": test["category_name"], "y": yte, "p": pte_best})
                  .groupby("cat").apply(lambda g: pd.Series({"n": len(g), "MAE": float(np.mean(np.abs(g.y - g.p)))}),
                                        include_groups=False)
                  .sort_values("n", ascending=False).reset_index())
    sample = pd.DataFrame({"actual": yte[:400], "predicted": pte_best[:400]}).round(2)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    # Trung bình đặc trưng trên train (để giải thích đóng góp của mô hình tuyến tính)
    feature_means = None
    if hasattr(best_model, "named_steps"):
        feature_means = np.asarray(best_model.named_steps["prep"].transform(Xtr).mean(axis=0)).ravel()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": best_model, "name": best, "log_resid_q10": q_lo, "log_resid_q90": q_hi,
                 "feature_means": feature_means},
                ARTIFACTS_DIR / "salary_model.joblib", compress=3)
    report = {
        "task": "salary", "target": "salary_avg (triệu VNĐ/tháng)", "best_model": best,
        "n_train": len(train), "n_val": len(val), "n_test": len(test), "filtered_range": [SAL_MIN, SAL_MAX],
        "results": results, "error_by_category": err_by_cat.to_dict(orient="records"),
        "scatter_sample": sample.to_dict(orient="records"),
        "paper_reference": {"note": "Bài báo VietJobs (LREC 2026), Bảng 4: fine-tune trên cả hai bộ dữ liệu (Fine-tuned on Both), chấm trên tập test VietJobs",
                            "model": "Llama-SEA-LION-v3-8B-IT", "RMSE": 10.24, "R2": 0.23},
    }
    run_id = record_run("salary", report, results, best, "artifacts/salary_model.joblib")
    print(f"  - Đã ghi kết quả vào PostgreSQL (ml_training_runs.run_id={run_id})")
    print(f"[Lương] Xong trong {time.time() - t0:.0f}s")
    return report


if __name__ == "__main__":
    run()
