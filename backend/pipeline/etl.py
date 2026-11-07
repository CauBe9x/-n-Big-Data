"""ETL: đọc VietJobs.csv -> làm sạch -> lưu bảng đã xử lý -> nạp vào PostgreSQL (database/schema.sql).

Chạy:  python -m pipeline.etl            (từ thư mục backend/)
"""
from __future__ import annotations

import argparse
import re
import time

import pandas as pd
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.config import PROCESSED_DIR, RAW_CSV
from app.db import (Category, Job, JobCategory, JobLanguage, JobSkill, Language, Province, Skill, create_schema,
                    engine)

from . import cleaning as C
from .runlog import tracked

PROCESSED_FILE = PROCESSED_DIR / "jobs_clean.pkl"


def _clean_text(v, limit: int | None = None):
    if C.is_missing(v):
        return None
    s = str(v).strip()
    return s[:limit] if limit else s


def _title_key(t) -> str:
    """'Kế Toán Thanh Toán - Lương 12tr (HN)' -> 'ke toan thanh toan'."""
    head = re.split(r"\s[-–|/]\s|\(|,", str(t))[0]
    return C.ascii_key(re.sub(r"\d+", " ", head))


def clean_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    n0 = len(df)
    df = df[~df["job_title"].apply(C.is_missing)].copy()
    df["category"] = df["category"].fillna("chưa_phân_loại").astype(str).str.strip().str.lower()

    # TopCV liệt kê cùng một tin dưới nhiều ngành -> gộp thành 1 tin, giữ danh sách ngành
    key = ["job_title", "location", "description"]
    df["_k"] = df[key].astype(str).agg("\x1f".join, axis=1)
    cats = df.groupby("_k", sort=False)["category"].agg(lambda s: list(dict.fromkeys(s)))
    n_rows = df.groupby("_k", sort=False).size()
    df = df.drop_duplicates("_k").reset_index(drop=True)
    df["category_slugs"] = df["_k"].map(cats)
    df["source_rows"] = df["_k"].map(n_rows).astype(int)
    df = df.drop(columns="_k")
    multi = int((df["category_slugs"].map(len) > 1).sum())
    print(f"  - Gộp {n0 - len(df)} dòng trùng -> {len(df)} tin duy nhất ({multi} tin thuộc >1 ngành)")

    loc = [C.normalize_location(l, c) for l, c in zip(df["location"], df["country"])]
    df["province"] = [p for p, _ in loc]
    df["provinces_all"] = [a for _, a in loc]

    df["experience_years"] = df["experience_required"].apply(C.parse_experience)
    df["experience_bucket"] = df["experience_years"].apply(C.experience_bucket)

    sal = [C.parse_salary(a, b, c) for a, b, c in zip(df["salary_min"], df["salary_max"], df["salary_avg"])]
    df["sal_min"] = [s[0] for s in sal]
    df["sal_max"] = [s[1] for s in sal]
    df["sal_avg"] = [s[2] for s in sal]
    df["is_negotiable"] = df["sal_avg"].isna()

    df["tech_skills"] = df["technical_skills"].apply(lambda v: C.normalize_skills(C.parse_list(v)))
    df["soft_skill_list"] = df["soft_skills"].apply(lambda v: C.normalize_skills(C.parse_list(v)))
    df["language_list"] = df["languages_required"].apply(C.parse_languages)
    df["qualification_list"] = df["qualifications"].apply(C.parse_list)
    df["benefit_list"] = df["benefits"].apply(C.parse_list)

    # Ngành chính: trong các ngành của tin, chọn ngành xuất hiện nhiều nhất với cùng chức danh (rút gọn)
    # trên toàn bộ dữ liệu -> "Kế toán thanh toán" thuộc Tài chính dù được crawl ở mục Du lịch trước.
    tkey = df["job_title"].map(_title_key)
    pair_count = (df.assign(t=tkey).explode("category_slugs").groupby(["t", "category_slugs"]).size().to_dict())
    df["category_slugs"] = [sorted(l, key=lambda c, t=t: -pair_count.get((t, c), 0)) for l, t in zip(df["category_slugs"], tkey)]
    df["category_slug"] = df["category_slugs"].str[0]
    df["category_name"] = df["category_slug"].apply(C.category_display_name)
    df["category_names"] = df["category_slugs"].apply(lambda l: [C.category_display_name(x) for x in l])
    df["contract_type"] = df["contract_type"].fillna("Không rõ").astype(str).str.strip()
    df["title"] = df["job_title"].astype(str).str.strip()
    df["id"] = range(1, len(df) + 1)

    keep = ["id", "title", "location", "province", "provinces_all", "country", "experience_required",
            "experience_years", "experience_bucket", "contract_type", "salary", "sal_min", "sal_max", "sal_avg",
            "is_negotiable", "working_hours", "qualification_list", "benefit_list", "description",
            "requirements_text", "category_slug", "category_name", "category_slugs", "category_names", "source_rows", "tech_skills", "soft_skill_list", "language_list"]
    return df[keep]


def load_into_db(df: pd.DataFrame) -> None:
    create_schema()  # chạy database/schema.sql: tạo lại bảng, khoá, ràng buộc, view
    all_slugs = sorted({c for l in df["category_slugs"] for c in l})
    cats = [(c, C.category_display_name(c)) for c in all_slugs]
    cat_id = {slug: i + 1 for i, (slug, _) in enumerate(cats)}
    provs = sorted(df["province"].unique())
    prov_rows = [dict(id=i + 1, name=p, region=C.province_region(p)) for i, p in enumerate(provs)]
    prov_id = {p: i + 1 for i, p in enumerate(provs)}

    skill_id: dict[tuple[str, str], int] = {}
    for kind, col in (("technical", "tech_skills"), ("soft", "soft_skill_list")):
        for lst in df[col]:
            for s in lst:
                skill_id.setdefault((s, kind), len(skill_id) + 1)
    lang_id: dict[str, int] = {}
    for lst in df["language_list"]:
        for l in lst:
            lang_id.setdefault(l, len(lang_id) + 1)

    jobs, job_skills, job_langs, job_cats = [], [], [], []
    for r in df.itertuples(index=False):
        jobs.append(dict(
            id=r.id, title=r.title[:300], title_key=C.ascii_key(r.title)[:300], location_raw=_clean_text(r.location, 300), province_id=prov_id[r.province],
            country=_clean_text(r.country, 60), experience_raw=_clean_text(r.experience_required, 60),
            experience_years=None if pd.isna(r.experience_years) else float(r.experience_years),
            experience_bucket=r.experience_bucket, contract_type=r.contract_type[:60], salary_raw=_clean_text(r.salary, 120),
            salary_min=None if pd.isna(r.sal_min) else float(r.sal_min),
            salary_max=None if pd.isna(r.sal_max) else float(r.sal_max),
            salary_avg=None if pd.isna(r.sal_avg) else float(r.sal_avg), is_negotiable=bool(r.is_negotiable),
            working_hours=_clean_text(r.working_hours), qualifications=list(r.qualification_list),
            benefits=list(r.benefit_list), description=_clean_text(r.description),
            requirements_text=_clean_text(r.requirements_text), category_id=cat_id[r.category_slug],
            source_rows=int(r.source_rows)))
        for c in r.category_slugs:
            job_cats.append(dict(job_id=r.id, category_id=cat_id[c], is_primary=(c == r.category_slug)))
        for s in r.tech_skills:
            job_skills.append(dict(job_id=r.id, skill_id=skill_id[(s, "technical")]))
        for s in r.soft_skill_list:
            job_skills.append(dict(job_id=r.id, skill_id=skill_id[(s, "soft")]))
        for l in r.language_list:
            job_langs.append(dict(job_id=r.id, language_id=lang_id[l]))

    # ORM bulk insert (khoá dict = tên thuộc tính ORM, vd id -> cột job_id)
    with Session(engine) as conn, conn.begin():
        conn.execute(insert(Category), [dict(id=cat_id[s], slug=s, name=n) for s, n in cats])
        conn.execute(insert(Province), prov_rows)
        conn.execute(insert(Skill), [dict(id=i, name=n, kind=k) for (n, k), i in skill_id.items()])
        if lang_id:
            conn.execute(insert(Language), [dict(id=i, name=n) for n, i in lang_id.items()])
        for i in range(0, len(jobs), 5000):
            conn.execute(insert(Job), jobs[i:i + 5000])
        conn.execute(insert(JobCategory), job_cats)
        for i in range(0, len(job_skills), 20000):
            conn.execute(insert(JobSkill), job_skills[i:i + 20000])
        # đồng bộ các sequence SERIAL với id đã chèn tay
        for table, col in (("provinces", "province_id"), ("categories", "category_id"), ("skills", "skill_id"),
                           ("languages", "language_id")):
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                              f"COALESCE((SELECT max({col}) FROM {table}), 1))"))
        if job_langs:
            conn.execute(insert(JobLanguage), job_langs)
    print(f"  - Nạp CSDL: {len(jobs)} jobs, {len(cats)} ngành, {len(provs)} tỉnh/thành, "
          f"{len(job_cats)} liên kết job-ngành, {len(skill_id)} kỹ năng, {len(job_skills)} liên kết job-kỹ năng, {len(lang_id)} ngôn ngữ")


def _summary(df: pd.DataFrame) -> dict:
    return {"rows_in": int(df["source_rows"].sum()), "rows_out": len(df),
            "detail": {"provinces": int(df["province"].nunique()),
                       "categories": len({c for l in df["category_slugs"] for c in l})}}


@tracked("etl", _summary)
def run(csv_path=RAW_CSV) -> pd.DataFrame:
    t0 = time.time()
    if not csv_path.exists():
        # Chưa có file -> tự tải từ Hugging Face (hoặc tự đặt VietJobs.csv vào data/raw/)
        import subprocess
        import sys

        from app.config import ROOT_DIR
        print(f"Không thấy {csv_path} -> tải từ Hugging Face")
        subprocess.check_call([sys.executable, str(ROOT_DIR / "scripts" / "download_data.py")])
    print(f"[ETL] Đọc {csv_path}")
    raw = pd.read_csv(csv_path)
    print(f"  - {len(raw)} dòng, {raw.shape[1]} cột")
    df = clean_dataframe(raw)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_pickle(PROCESSED_FILE)
    print(f"  - Lưu bảng đã làm sạch: {PROCESSED_FILE}")
    load_into_db(df)
    print(f"[ETL] Xong trong {time.time() - t0:.1f}s")
    return df


def load_clean() -> pd.DataFrame:
    if not PROCESSED_FILE.exists():
        return run()
    return pd.read_pickle(PROCESSED_FILE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(RAW_CSV))
    args = ap.parse_args()
    from pathlib import Path
    run(Path(args.csv))
