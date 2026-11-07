"""Bài toán 2 – Dự đoán kỹ năng cần thiết (phân loại đa nhãn).

Đầu vào: chức danh (+ mô tả nếu có). Nhãn: các kỹ năng chuyên môn & kỹ năng mềm phổ biến
(xuất hiện >= MIN_FREQ tin, tối đa MAX_LABELS nhãn) sau khi chuẩn hoá tên kỹ năng.
Mô hình chính: One-vs-Rest Logistic Regression trên TF-IDF của CHỈ chức danh (kịch bản UI);
so với baseline "kỹ năng phổ biến nhất của ngành" và biến thể có thêm mô tả công việc.
Đánh giá: Precision@k, Recall@k, Micro/Macro-F1 (ngưỡng chọn trên tập val).

Chạy: python -m pipeline.train_skills
"""
from __future__ import annotations

import time
from collections import Counter

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, MultiLabelBinarizer

from app.config import ARTIFACTS_DIR

from .common import record_run, split_80_10_10
from .etl import load_clean
from .runlog import tracked
from .features import text_frame, text_preprocessor, to_sorted_csr

MAX_LABELS = 300


def _labels(row) -> list[str]:
    return [f"T::{s}" for s in row.tech_skills] + [f"S::{s}" for s in row.soft_skill_list]


def _ranking_metrics(Y, P, k_list=(5, 10)) -> dict:
    out = {}
    order = np.argsort(-P, axis=1)
    has = Y.sum(axis=1) > 0
    for k in k_list:
        topk = order[:, :k]
        hits = np.take_along_axis(Y, topk, axis=1).sum(axis=1)
        out[f"Precision@{k}"] = float(np.mean(hits[has] / k))
        out[f"Recall@{k}"] = float(np.mean(hits[has] / np.maximum(Y[has].sum(axis=1), 1)))
    return out


def _f1(Y, P, thr) -> dict:
    pred = (P >= thr).astype(int)
    return {"Micro_F1": float(f1_score(Y, pred, average="micro", zero_division=0)),
            "Macro_F1": float(f1_score(Y, pred, average="macro", zero_division=0))}


class CategoryPopularityBaseline:
    """Điểm của kỹ năng = tần suất xuất hiện trong ngành (tập train)."""

    def fit(self, cats, Y):
        self.freq_ = {}
        for c in np.unique(cats):
            m = cats == c
            self.freq_[c] = Y[m].mean(axis=0)
        self.global_ = Y.mean(axis=0)
        return self

    def predict_proba(self, cats):
        return np.vstack([self.freq_.get(c, self.global_) for c in cats])


def _summary(r: dict) -> dict:
    return {"rows_in": r["n_train"] + r["n_val"] + r["n_test"], "rows_out": r["n_test"],
            "detail": {"best_model": r["best_model"]}}


@tracked("skills", _summary)
def run() -> dict:
    t0 = time.time()
    df = load_clean()
    df = df.assign(labels=[_labels(r) for r in df.itertuples(index=False)])
    df = df[df["labels"].map(len) > 0].reset_index(drop=True)

    min_freq = max(15, int(0.001 * len(df)))
    freq = Counter(l for ls in df["labels"] for l in ls)
    vocab = [l for l, c in freq.most_common(MAX_LABELS) if c >= min_freq]
    vocab_set = set(vocab)
    df["labels"] = df["labels"].map(lambda ls: [l for l in ls if l in vocab_set])
    df = df[df["labels"].map(len) > 0].reset_index(drop=True)
    print(f"[Kỹ năng] {len(df)} tin có kỹ năng, {len(vocab)} nhãn (tần suất >= {min_freq})")

    mlb = MultiLabelBinarizer(classes=vocab)
    train, val, test = split_80_10_10(df)
    Ytr, Yva, Yte = (mlb.fit_transform(d["labels"]) for d in (train, val, test))

    def X(d, title_only=False):
        return text_frame(list(d["title"]), None if title_only else
                          (d["description"].fillna("") + " . " + d["requirements_text"].fillna("")).tolist())

    def ovr(use_desc: bool) -> Pipeline:
        return Pipeline([
            ("prep", text_preprocessor(use_desc=use_desc)),
            ("csr", FunctionTransformer(to_sorted_csr, accept_sparse=True)),
            ("clf", OneVsRestClassifier(LogisticRegression(C=4.0, solver="liblinear", max_iter=500), n_jobs=-1)),
        ])

    thresholds = np.arange(0.05, 0.61, 0.05)

    def pick_thr(Pval):
        return float(max(thresholds, key=lambda th: _f1(Yva, Pval, th)["Micro_F1"]))

    results, probs = {}, {}

    # 1) Baseline: kỹ năng phổ biến nhất trong ngành (giả định đã biết ngành)
    base = CategoryPopularityBaseline().fit(train["category_slug"].to_numpy(), Ytr)
    thr = pick_thr(base.predict_proba(val["category_slug"].to_numpy()))
    P = base.predict_proba(test["category_slug"].to_numpy())
    results["Baseline (phổ biến theo ngành)"] = {"test": {**_ranking_metrics(Yte, P), **_f1(Yte, P, thr)}, "threshold": thr}

    # 2) Mô hình chính – CHỈ chức danh (đúng kịch bản người dùng nhập tên vị trí trên UI)
    # 3) Mô hình đối chứng – chức danh + mô tả/yêu cầu (gần với "trích xuất" vì kỹ năng thường nằm sẵn trong văn bản)
    fitted = {}
    for name, use_desc in (("OvR LogReg – chỉ chức danh", False), ("OvR LogReg – chức danh + mô tả", True)):
        t = time.time()
        m = ovr(use_desc).fit(X(train, title_only=not use_desc), Ytr)
        thr = pick_thr(m.predict_proba(X(val, title_only=not use_desc)))
        P = m.predict_proba(X(test, title_only=not use_desc))
        results[name] = {"test": {**_ranking_metrics(Yte, P), **_f1(Yte, P, thr)}, "threshold": thr,
                         "train_seconds": round(time.time() - t, 1)}
        fitted[name], probs[name] = m, P

    for name, r in results.items():
        print(f"  - {name:32s} " + "  ".join(f"{k}={v:.3f}" for k, v in r["test"].items()))

    best = "OvR LogReg – chỉ chức danh"
    model, best_thr, Pte = fitted[best], results[best]["threshold"], probs[best]

    # F1 theo từng nhãn phổ biến (mô hình chính)
    pred = (Pte >= best_thr).astype(int)
    per_label = []
    for j, lab in enumerate(vocab[:40]):
        per_label.append({"skill": lab.split("::", 1)[1], "kind": "technical" if lab.startswith("T::") else "soft",
                          "support": int(Yte[:, j].sum()),
                          "f1": float(f1_score(Yte[:, j], pred[:, j], zero_division=0))})

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "labels": vocab, "threshold": best_thr, "name": best},
                ARTIFACTS_DIR / "skills_model.joblib", compress=3)
    report = {"task": "skills", "best_model": best, "n_labels": len(vocab),
              "n_train": len(train), "n_val": len(val), "n_test": len(test), "results": results,
              "per_label": per_label}
    run_id = record_run("skills", report, results, best, "artifacts/skills_model.joblib")
    print(f"  - Đã ghi kết quả vào PostgreSQL (ml_training_runs.run_id={run_id})")
    print(f"[Kỹ năng] Xong trong {time.time() - t0:.0f}s")
    return report


if __name__ == "__main__":
    run()
