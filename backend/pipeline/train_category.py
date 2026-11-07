"""Bài toán 3 – Phân loại ngành nghề (16 lớp) từ tiêu đề + mô tả công việc.

So sánh: Complement Naive Bayes · Logistic Regression · Linear SVM trên TF-IDF.
Lưu ý dữ liệu: ~21% tin được TopCV đăng dưới nhiều ngành. Ta chia train/val/test theo TIN, huấn luyện trên mọi
cặp (tin, ngành), và chấm "đúng" nếu ngành dự đoán thuộc tập ngành của tin (kèm số liệu "chặt" so với ngành chính).
Đánh giá: Accuracy, Macro-F1, ma trận nhầm lẫn; kèm thiết lập "chỉ mô tả" để đối chiếu bài báo.

Chạy: python -m pipeline.train_category
"""
from __future__ import annotations

import time

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.config import ARTIFACTS_DIR, RANDOM_STATE

from .common import record_run, split_80_10_10
from . import cleaning as C
from .etl import load_clean
from .runlog import tracked
from .features import text_frame, text_preprocessor


def _metrics(y, p) -> dict:
    return {"Accuracy": float(accuracy_score(y, p)), "Macro_F1": float(f1_score(y, p, average="macro")),
            "Weighted_F1": float(f1_score(y, p, average="weighted"))}


def _frame(d, use_title=True):
    titles = d["title"] if use_title else [""] * len(d)
    desc = (d["description"].fillna("") + " . " + d["requirements_text"].fillna("")).tolist()
    return text_frame(list(titles), desc)


def _resolve(true_sets, pred, primary):
    """Nhãn 'thật' để chấm: nếu dự đoán nằm trong tập ngành của tin -> coi là đúng, ngược lại dùng ngành chính."""
    return [p if p in ts else pr for ts, p, pr in zip(true_sets, pred, primary)]


def _eval(d, pred) -> dict:
    sets = [set(l) for l in d["category_slugs"]]
    lenient = _resolve(sets, pred, d["category_slug"])
    m = _metrics(lenient, pred)
    strict = _metrics(d["category_slug"], pred)
    return {**m, "Accuracy_strict": strict["Accuracy"], "Macro_F1_strict": strict["Macro_F1"]}


def _explode(d):
    """Tin thuộc k ngành -> k mẫu huấn luyện (cùng văn bản, khác nhãn)."""
    e = d.explode("category_slugs").reset_index(drop=True)
    return e, e["category_slugs"]


def _summary(r: dict) -> dict:
    return {"rows_in": r["n_train"] + r["n_val"] + r["n_test"], "rows_out": r["n_test"],
            "detail": {"best_model": r["best_model"]}}


@tracked("category", _summary)
def run() -> dict:
    t0 = time.time()
    df = load_clean()
    counts = df["category_slug"].value_counts()
    df = df[df["category_slug"].isin(counts[counts >= 10].index)].reset_index(drop=True)
    # Chia theo TIN (không phải theo dòng) -> một tin không thể vừa ở train vừa ở test
    train, val, test = split_80_10_10(df, stratify_col="category_slug")
    tr_rows, ytr = _explode(train)
    Xtr, Xva, Xte = _frame(tr_rows), _frame(val), _frame(test)
    multi = float((df["category_slugs"].map(len) > 1).mean() * 100)
    print(f"[Ngành] {len(df)} tin ({multi:.1f}% thuộc >1 ngành), {df['category_slug'].nunique()} lớp; "
          f"train={len(train)} tin ({len(tr_rows)} mẫu) val={len(val)} test={len(test)}")

    candidates = {
        "Complement Naive Bayes": ComplementNB(alpha=0.3),
        # class_weight="balanced": bù cho lớp nhỏ (Nông nghiệp, Ngôn ngữ…) bị lớp lớn (Kinh doanh) lấn át
        "Logistic Regression (cân bằng lớp)": LogisticRegression(C=4.0, max_iter=1000, class_weight="balanced",
                                                                random_state=RANDOM_STATE),
        "Linear SVM": LinearSVC(C=0.3, random_state=RANDOM_STATE),
        "Linear SVM (cân bằng lớp)": LinearSVC(C=0.1, class_weight="balanced", random_state=RANDOM_STATE),
    }
    results, fitted = {}, {}
    for name, clf in candidates.items():
        t = time.time()
        pipe = Pipeline([("prep", text_preprocessor()), ("clf", clf)]).fit(Xtr, ytr)
        results[name] = {"val": _eval(val, pipe.predict(Xva)), "test": _eval(test, pipe.predict(Xte)),
                         "train_seconds": round(time.time() - t, 1)}
        fitted[name] = pipe
        r = results[name]["test"]
        print(f"  - {name:24s} val F1={results[name]['val']['Macro_F1']:.3f} | test Acc={r['Accuracy']:.3f} "
              f"F1={r['Macro_F1']:.3f} (chặt: Acc={r['Accuracy_strict']:.3f}) ({results[name]['train_seconds']}s)")

    best = max(results, key=lambda k: results[k]["val"]["Macro_F1"])
    model = fitted[best]
    print(f"  => Tốt nhất: {best}")

    # Thiết lập giống bài báo: chỉ dùng mô tả công việc (không có tiêu đề)
    paper_pipe = Pipeline([("prep", text_preprocessor(use_title=False)),
                           ("clf", candidates[best].__class__(**candidates[best].get_params()))])
    paper_pipe.fit(_frame(tr_rows, use_title=False), ytr)
    results[best]["test_description_only"] = _eval(test, paper_pipe.predict(_frame(test, use_title=False)))
    print(f"  - Chỉ dùng mô tả (giống bài báo): {results[best]['test_description_only']}")

    pred = model.predict(Xte)
    y_true = _resolve([set(l) for l in test["category_slugs"]], pred, test["category_slug"])
    labels = sorted(df["category_slug"].unique())
    names = {c: C.category_display_name(c) for c in labels}
    cm = confusion_matrix(y_true, pred, labels=labels)
    rep = classification_report(y_true, pred, labels=labels, output_dict=True, zero_division=0)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "name": best, "labels": labels, "names": names},
                ARTIFACTS_DIR / "category_model.joblib", compress=3)
    report = {
        "task": "category", "best_model": best, "n_train": len(train), "n_val": len(val), "n_test": len(test),
        "multi_label_pct": multi, "results": results,
        "labels": [names[l] for l in labels], "confusion_matrix": cm.tolist(),
        "per_class": [{"category": names[l], "precision": rep[l]["precision"], "recall": rep[l]["recall"],
                       "f1": rep[l]["f1-score"], "support": int(rep[l]["support"])} for l in labels],
        "paper_reference": {"note": "Bài báo VietJobs (LREC 2026): LLM few-shot tốt nhất, đầu vào chỉ là mô tả",
                            "model": "Qwen2.5-7B-Instruct (few-shot)", "Accuracy": 0.47, "Macro_F1": 0.42},
    }
    run_id = record_run("category", report, results, best, "artifacts/category_model.joblib")
    print(f"  - Đã ghi kết quả vào PostgreSQL (ml_training_runs.run_id={run_id})")
    print(f"[Ngành] Xong trong {time.time() - t0:.0f}s")
    return report


if __name__ == "__main__":
    run()
