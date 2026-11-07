"""Khai phá dữ liệu:
  (a) Thống kê "giá trị" của kỹ năng: lương trung vị khi tin yêu cầu kỹ năng đó so với toàn thị trường.
  (b) Luật kết hợp (FP-Growth): {kỹ năng...} => {kỹ năng | Ngành=... | Lương=Cao}.
  (c) Phân cụm tin tuyển dụng (TF-IDF chức danh ⊕ TF-IDF kỹ năng -> SVD -> K-Means, chọn k theo silhouette).

Chạy: python -m pipeline.mining
"""
from __future__ import annotations

import re
import time
from collections import Counter

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from sqlalchemy import delete, insert, select

from app.config import RANDOM_STATE
from app.db import (AssociationRule, Category, Cluster, ClusterKScore, JobCluster, MiningRun, RuleAntecedent,
                    SessionLocal, Skill, SkillSalaryStat)

from .common import to_json
from .etl import load_clean
from .features import TITLE_STOPWORDS, clean_title, split_pipe
from .runlog import tracked

try:
    from mlxtend.frequent_patterns import association_rules, fpgrowth
    from mlxtend.preprocessing import TransactionEncoder
except ImportError:  # pragma: no cover
    fpgrowth = None


# ---------------------------------------------------------------------------
def skill_value(df: pd.DataFrame, min_count: int = 30) -> list[dict]:
    paid = df[df["sal_avg"].between(1, 150)]
    overall = float(paid["sal_avg"].median())
    rows = []
    for kind, col in (("technical", "tech_skills"), ("soft", "soft_skill_list")):
        exploded = paid[["sal_avg", col, "category_name"]].explode(col).dropna(subset=[col])
        total_counts = df[col].explode().value_counts()
        for skill, g in exploded.groupby(col):
            if len(g) < min_count:
                continue
            med = float(g["sal_avg"].median())
            rows.append({"skill": skill, "kind": kind, "n_jobs": int(total_counts.get(skill, len(g))),
                         "n_with_salary": int(len(g)), "median_salary": med,
                         "mean_salary": float(g["sal_avg"].mean()),
                         "premium_%": (med / overall - 1) * 100,
                         "top_category": g["category_name"].mode().iat[0]})
    rows.sort(key=lambda r: -r["n_jobs"])
    return rows


# ---------------------------------------------------------------------------
def association_mining(df: pd.DataFrame, max_rules: int = 600) -> dict:
    if fpgrowth is None:
        return {"rules": [], "error": "Chưa cài mlxtend"}
    paid = df["sal_avg"].between(1, 150)
    q75 = float(df.loc[paid, "sal_avg"].quantile(0.75))
    q25 = float(df.loc[paid, "sal_avg"].quantile(0.25))

    transactions = []
    for r in df.itertuples(index=False):
        items = set(r.tech_skills) | set(r.soft_skill_list)
        if not items:
            continue
        items.update(f"Ngành={c}" for c in r.category_names)
        if pd.notna(r.sal_avg) and 1 <= r.sal_avg <= 150:
            items.add("Lương=Cao" if r.sal_avg >= q75 else ("Lương=Thấp" if r.sal_avg <= q25 else "Lương=Trung bình"))
        transactions.append(sorted(items))

    # Giữ các item đủ phổ biến để FP-Growth chạy nhanh
    n = len(transactions)
    cnt = Counter(i for t in transactions for i in t)
    min_support = 0.008 if n > 20000 else 0.02
    keep = {i for i, c in cnt.items() if c / n >= min_support}
    transactions = [[i for i in t if i in keep] for t in transactions]
    transactions = [t for t in transactions if t]

    te = TransactionEncoder()
    onehot = pd.DataFrame(te.fit(transactions).transform(transactions, sparse=False), columns=te.columns_)
    freq = fpgrowth(onehot, min_support=min_support, use_colnames=True, max_len=3)
    rules = association_rules(freq, metric="lift", min_threshold=1.2)
    rules = rules[(rules["confidence"] >= 0.25)]
    # Vế trái chỉ chứa kỹ năng; vế phải 1 item
    rules = rules[rules["antecedents"].map(lambda s: all("=" not in x for x in s))]
    rules = rules[rules["consequents"].map(len) == 1]

    def kind_of(item: str) -> str:
        if item.startswith("Ngành="):
            return "category"
        if item.startswith("Lương="):
            return "salary"
        return "skill"

    out = []
    for r in rules.sort_values(["lift", "confidence"], ascending=False).itertuples(index=False):
        cons = next(iter(r.consequents))
        out.append({"antecedents": sorted(r.antecedents), "consequent": cons, "consequent_type": kind_of(cons),
                    "support": float(r.support), "confidence": float(r.confidence), "lift": float(r.lift)})
    # Cân bằng 3 loại vế phải
    by_type: dict[str, list] = {"skill": [], "category": [], "salary": []}
    for r in out:
        by_type[r["consequent_type"]].append(r)
    final = by_type["salary"][:150] + by_type["category"][:200] + by_type["skill"][: max_rules - 350]
    return {"n_transactions": n, "min_support": min_support, "salary_thresholds": {"Thấp<=": q25, "Cao>=": q75},
            "n_frequent_itemsets": int(len(freq)), "n_rules_total": int(len(out)), "rules": final}


# ---------------------------------------------------------------------------
def _short_title(t: str) -> str:
    """'Nhân Viên Kinh Doanh - Thu Nhập 20 Triệu (HN)' -> 'nhân viên kinh doanh'."""
    t = re.split(r"\s[-–|/]\s|\(|,", str(t))[0]
    return re.sub(r"\s+", " ", t).strip().lower()


def clustering(df: pd.DataFrame, k_range=range(8, 41, 4), n_points: int = 3000) -> dict:
    # Hai khối đặc trưng riêng biệt để không sinh bigram lai giữa chức danh và kỹ năng:
    #   (1) TF-IDF 1–2 gram của chức danh (bỏ từ chung chung), (2) TF-IDF kỹ năng chuyên môn (mỗi kỹ năng = 1 token)
    tvec = TfidfVectorizer(min_df=5, max_df=0.2, ngram_range=(1, 2), max_features=20000, sublinear_tf=True,
                           stop_words=TITLE_STOPWORDS)
    svec = TfidfVectorizer(tokenizer=split_pipe, token_pattern=None, lowercase=False, min_df=10, sublinear_tf=True)
    Xt = tvec.fit_transform([clean_title(t) for t in df["title"]])
    Xs = svec.fit_transform(["|".join(a) for a in df["tech_skills"]])
    X = sparse.hstack([Xt, 0.7 * Xs]).tocsr()
    svd = TruncatedSVD(n_components=80, random_state=RANDOM_STATE)
    Z = normalize(svd.fit_transform(X))

    rng = np.random.default_rng(RANDOM_STATE)
    sample_idx = rng.choice(len(Z), size=min(6000, len(Z)), replace=False)
    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=3, random_state=RANDOM_STATE).fit(Z)
        scores[k] = float(silhouette_score(Z[sample_idx], km.labels_[sample_idx]))
        print(f"    k={k:2d} silhouette={scores[k]:.4f}")
    best_k = max(scores, key=scores.get)
    km = KMeans(n_clusters=best_k, n_init=10, random_state=RANDOM_STATE).fit(Z)
    labels = km.labels_

    tterms = np.array(tvec.get_feature_names_out())
    centroids = svd.inverse_transform(km.cluster_centers_)[:, : len(tterms)]
    short = df["title"].map(_short_title)
    n_all = len(df)
    global_tech = Counter(s for lst in df["tech_skills"] for s in lst)
    clusters = []
    for c in range(best_k):
        m = labels == c
        sub = df[m]
        ranked = list(tterms[np.argsort(-centroids[c])[:30]])
        phrases = [u for u in ranked[:15] if " " in u]   # bỏ âm tiết đã nằm trong cụm từ ("toán" ⊂ "kế toán")
        top_terms = [t for t in ranked if " " in t or not any(t in u.split() for u in phrases)][:10]
        tech = Counter(s for lst in sub["tech_skills"] for s in lst)
        soft = Counter(s for lst in sub["soft_skill_list"] for s in lst)
        sal = sub["sal_avg"][sub["sal_avg"].between(1, 150)]
        common_titles = short[m].value_counts()
        # kỹ năng đặc trưng: xuất hiện ở >=5% tin của cụm và có lift (tỷ lệ trong cụm / tỷ lệ toàn bộ) cao nhất
        n_c = int(m.sum())
        distinct = sorted((sk for sk, cnt in tech.items() if cnt >= max(5, 0.05 * n_c)),
                          key=lambda sk: -(tech[sk] / n_c) / (global_tech[sk] / n_all))
        clusters.append({
            "id": int(c), "size": int(m.sum()),
            "label": common_titles.index[0].capitalize() if len(common_titles) else " ".join(top_terms[:2]),
            "top_terms": top_terms, "top_skills": [s for s, _ in tech.most_common(10)],
            "distinct_skills": distinct[:6],
            "top_soft_skills": [s for s, _ in soft.most_common(5)],
            "example_titles": [t.capitalize() for t in common_titles.head(6).index],
            "median_salary": float(sal.median()) if len(sal) else None,
            "top_categories": [{"name": k, "share": float(v)} for k, v in
                               sub["category_name"].value_counts(normalize=True).head(3).items()],
        })
    clusters.sort(key=lambda c: -c["size"])
    # Nhãn trùng (vd. nhiều cụm "Nhân viên kinh doanh") -> thêm 2 kỹ năng đặc trưng để phân biệt
    dup = Counter(c["label"] for c in clusters)
    for c in clusters:
        if dup[c["label"]] > 1 and c["distinct_skills"]:
            c["label"] = f"{c['label']} ({', '.join(c['distinct_skills'][:2])})"

    # Toạ độ 2D để vẽ scatter (PCA trên không gian SVD đã chuẩn hoá)
    from sklearn.decomposition import PCA
    pts_idx = rng.choice(len(Z), size=min(n_points, len(Z)), replace=False)
    P2 = PCA(n_components=2, random_state=RANDOM_STATE).fit_transform(Z[pts_idx])
    points = [{"x": round(float(x), 4), "y": round(float(y), 4), "c": int(labels[i]), "t": df["title"].iat[i][:60]}
              for (x, y), i in zip(P2, pts_idx)]
    return {"k": int(best_k), "silhouette": scores, "clusters": clusters, "points": points,
            "explained_variance_svd": float(svd.explained_variance_ratio_.sum()),
            "_labels": labels, "_pts_idx": pts_idx, "_P2": P2}


# ---------------------------------------------------------------------------
# Ghi kết quả vào PostgreSQL
# ---------------------------------------------------------------------------
def _skill_lookup(db) -> dict[str, int]:
    """tên kỹ năng -> skill_id (ưu tiên bản 'technical' nếu tên có ở cả hai loại)."""
    out: dict[str, int] = {}
    for sid, name, kind in db.execute(select(Skill.id, Skill.name, Skill.kind)).all():
        if name not in out or kind == "technical":
            out[name] = sid
    return out


def _new_run(db, kind: str, params: dict) -> int:
    db.execute(delete(MiningRun).where(MiningRun.kind == kind))   # chỉ giữ lần chạy mới nhất
    run = MiningRun(kind=kind, params=to_json(params))
    db.add(run)
    db.flush()
    return run.id


def save_skill_value(db, rows: list[dict], skill_id: dict, cat_id: dict) -> None:
    run_id = _new_run(db, "skill_salary", {"min_count": 30, "salary_range": [1, 150]})
    data = []
    for r in rows:
        sid = db.scalar(select(Skill.id).where(Skill.name == r["skill"], Skill.kind == r["kind"]))
        if sid is None:
            continue
        data.append(dict(run_id=run_id, skill_id=sid, n_jobs=r["n_jobs"], n_with_salary=r["n_with_salary"],
                         median_salary=r["median_salary"], mean_salary=r["mean_salary"],
                         premium_pct=r["premium_%"], top_category_id=cat_id.get(r["top_category"])))
    if data:
        db.execute(insert(SkillSalaryStat), data)


def save_rules(db, res: dict, skill_id: dict, cat_id: dict) -> int:
    params = {k: v for k, v in res.items() if k != "rules"}
    run_id = _new_run(db, "association_rules", params)
    n = 0
    for r in res["rules"]:
        ants = [skill_id[a] for a in r["antecedents"] if a in skill_id]
        if len(ants) != len(r["antecedents"]):
            continue
        cons = r["consequent"]
        row = AssociationRule(run_id=run_id, consequent_type=r["consequent_type"], consequent_label=cons,
                              support=r["support"], confidence=r["confidence"], lift=r["lift"])
        if r["consequent_type"] == "skill":
            if cons not in skill_id:
                continue
            row.consequent_skill_id = skill_id[cons]
        elif r["consequent_type"] == "category":
            cid = cat_id.get(cons.split("=", 1)[1])
            if cid is None:
                continue
            row.consequent_category_id = cid
        db.add(row)
        db.flush()
        db.execute(insert(RuleAntecedent), [dict(rule_id=row.id, skill_id=s) for s in sorted(set(ants))])
        n += 1
    return n


def save_clusters(db, df: pd.DataFrame, cl: dict) -> None:
    params = {"k": cl["k"], "k_range": sorted(cl["silhouette"]), "explained_variance_svd": cl["explained_variance_svd"],
              "features": "TF-IDF chức danh (1-2 gram) + 0.7 x TF-IDF kỹ năng chuyên môn -> SVD 80 -> L2 -> K-Means"}
    run_id = _new_run(db, "clustering", params)
    db.execute(insert(ClusterKScore), [dict(run_id=run_id, k=int(k), silhouette=v, is_chosen=(int(k) == cl["k"]))
                                       for k, v in cl["silhouette"].items()])
    label_to_id = {}
    for c in cl["clusters"]:
        row = Cluster(run_id=run_id, kmeans_label=c["id"], label=c["label"][:200], size=c["size"],
                      median_salary=c["median_salary"], top_terms=c["top_terms"], top_skills=c["top_skills"],
                      distinct_skills=c["distinct_skills"], top_soft_skills=c["top_soft_skills"],
                      example_titles=c["example_titles"], top_categories=to_json(c["top_categories"]))
        db.add(row)
        db.flush()
        label_to_id[c["id"]] = row.id
    pca = {int(i): (float(x), float(y)) for i, (x, y) in zip(cl["_pts_idx"], cl["_P2"])}
    ids = df["id"].to_numpy()
    rows = [dict(job_id=int(ids[i]), cluster_id=label_to_id[int(lab)],
                 pca_x=pca[i][0] if i in pca else None, pca_y=pca[i][1] if i in pca else None)
            for i, lab in enumerate(cl["_labels"])]
    for i in range(0, len(rows), 10000):
        db.execute(insert(JobCluster), rows[i:i + 10000])


@tracked("mining", lambda r: {"rows_in": r["jobs"], "rows_out": r["rules"], "detail": r})
def run() -> dict:
    t0 = time.time()
    df = load_clean()
    with SessionLocal() as db:
        skill_id = _skill_lookup(db)
        cat_id = {n: i for i, n in db.execute(select(Category.id, Category.name)).all()}

        print("[Khai phá] Giá trị kỹ năng ...")
        save_skill_value(db, skill_value(df), skill_id, cat_id)

        print("[Khai phá] Luật kết hợp (FP-Growth) ...")
        rules = association_mining(df)
        n = save_rules(db, rules, skill_id, cat_id)
        print(f"  - {rules.get('n_frequent_itemsets')} tập phổ biến, {n} luật được lưu (lift>=1.2, conf>=0.25)")

        print("[Khai phá] Phân cụm K-Means ...")
        cl = clustering(df)
        save_clusters(db, df, cl)
        print(f"  - Chọn k={cl['k']}")
        db.commit()
    print(f"[Khai phá] Đã ghi vào PostgreSQL. Xong trong {time.time() - t0:.0f}s")
    return {"jobs": len(df), "rules": n, "k": cl["k"]}


if __name__ == "__main__":
    run()
