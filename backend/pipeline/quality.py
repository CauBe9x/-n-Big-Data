"""Hồ sơ chất lượng dữ liệu: đo trực tiếp trên VietJobs.csv gốc và trên bảng đã làm sạch, ghi vào pipeline_runs.

Mọi con số trên trang "Chất lượng dữ liệu" đến từ đây, không có số nào viết tay.

Chạy: python -m pipeline.quality
"""
from __future__ import annotations

import re

import pandas as pd

from app.config import RAW_CSV

from . import cleaning as C
from .etl import load_clean
from .runlog import tracked

SAL_LO, SAL_HI = 1, 150
DUP_KEY = ["job_title", "location", "description"]

# Vai trò của từng cột gốc: dùng ở trang dữ liệu và DATA_DICTIONARY.md
COLUMN_NOTES = {
    "job_title": "Chức danh, đặc trưng chính của cả 3 mô hình",
    "location": "Địa điểm thô, chuẩn hoá về tỉnh/thành và miền",
    "country": "Quốc gia",
    "qualifications": "Bằng cấp (chuỗi list Python)",
    "technical_skills": "Kỹ năng chuyên môn do LLM trích xuất",
    "soft_skills": "Kỹ năng mềm do LLM trích xuất",
    "languages_required": "Ngoại ngữ yêu cầu; trống = không yêu cầu",
    "experience_required": "Kinh nghiệm dạng chữ, đổi sang số năm",
    "salary": "Chuỗi lương gốc",
    "contract_type": "Loại hợp đồng",
    "working_hours": "Thời gian làm việc",
    "benefits": "Phúc lợi",
    "description": "Mô tả công việc",
    "requirements_text": "Yêu cầu ứng viên dạng văn bản",
    "category": "Ngành TopCV (16 nhóm), một tin có thể lặp ở nhiều ngành",
    "salary_min": "Lương tối thiểu (triệu/tháng), 0 = thoả thuận",
    "salary_max": "Lương tối đa (triệu/tháng), 0 = thoả thuận",
    "salary_avg": "Lương trung bình dạng chữ",
}


def profile_raw(raw: pd.DataFrame) -> dict:
    n = len(raw)
    cols = []
    for c in raw.columns:
        s = raw[c]
        missing = int(s.isna().sum())
        cols.append({"name": c, "dtype": str(s.dtype), "missing": missing, "missing_pct": round(missing * 100 / n, 2),
                     "unique": int(s.nunique()), "note": COLUMN_NOTES.get(c, ""),
                     "sample": str(s.dropna().iloc[0])[:80] if s.notna().any() else None})

    smin, smax = raw["salary_min"], raw["salary_max"]
    negotiable = (smin == 0) & (smax == 0)
    disclosed = ~negotiable
    pair = pd.concat([smin, smax], axis=1).astype(float)
    avg = pair.where(pair > 0).mean(axis=1)
    return {
        "rows": n, "columns": raw.shape[1], "columns_profile": cols,
        "duplicates": {
            "full_row": int(raw.duplicated().sum()),
            "same_posting": int(raw.duplicated(DUP_KEY).sum()),
            "unique_postings": int(n - raw.duplicated(DUP_KEY).sum()),
        },
        "salary": {
            "negotiable_rows": int(negotiable.sum()),
            "negotiable_pct": round(float(negotiable.mean() * 100), 2),
            "min_gt_max": int(((smin > smax) & (smax > 0)).sum()),
            "below_range": int((disclosed & (avg < SAL_LO)).sum()),
            "above_range": int((disclosed & (avg > SAL_HI)).sum()),
            "max_value": float(max(smin.max(), smax.max())),
            "range_used": [SAL_LO, SAL_HI],
        },
        "date_columns": [c for c in raw.columns if re.search(r"date|posted|ngay", c, re.I)],
    }


def profile_cleaning(raw: pd.DataFrame, clean: pd.DataFrame) -> dict:
    raw_tech = {s.strip().lower() for v in raw["technical_skills"] for s in C.parse_list(v)}
    raw_soft = {s.strip().lower() for v in raw["soft_skills"] for s in C.parse_list(v)}
    tech = {s for l in clean["tech_skills"] for s in l}
    soft = {s for l in clean["soft_skill_list"] for s in l}
    return {
        "rows_out": len(clean),
        "multi_category_jobs": int((clean["category_slugs"].map(len) > 1).sum()),
        "steps": [
            {"field": "Tin tuyển dụng", "before": len(raw), "after": len(clean),
             "how": "Gộp dòng trùng theo (chức danh, địa điểm, mô tả), giữ mọi ngành"},
            {"field": "Cách ghi địa điểm", "before": int(raw["location"].nunique()),
             "after": int(clean["province"].nunique()), "how": "Bảng bí danh quận/huyện về tỉnh/thành"},
            {"field": "Tên kỹ năng chuyên môn", "before": len(raw_tech), "after": len(tech),
             "how": "Bỏ tiền tố/hậu tố, gộp bí danh"},
            {"field": "Tên kỹ năng mềm", "before": len(raw_soft), "after": len(soft),
             "how": "Bỏ tiền tố/hậu tố, gộp bí danh"},
            {"field": "Cách ghi kinh nghiệm", "before": int(raw["experience_required"].nunique()),
             "after": int(clean["experience_bucket"].nunique()), "how": "Đổi sang số năm rồi chia nhóm"},
        ],
    }


def _summary(rep: dict) -> dict:
    return {"rows_in": rep["raw"]["rows"], "rows_out": rep["clean"]["rows_out"], "detail": rep}


@tracked("quality", _summary)
def run() -> dict:
    print(f"[Chất lượng] Đọc {RAW_CSV}", flush=True)
    raw = pd.read_csv(RAW_CSV)
    print(f"  - {len(raw)} dòng, {raw.shape[1]} cột; đang đo thiếu/trùng/bất thường", flush=True)
    report = {"raw": profile_raw(raw)}
    report["clean"] = profile_cleaning(raw, load_clean())
    print(f"  - Trùng theo tin: {report['raw']['duplicates']['same_posting']}; "
          f"thoả thuận: {report['raw']['salary']['negotiable_pct']}%", flush=True)
    print("[Chất lượng] Xong", flush=True)
    return report


if __name__ == "__main__":
    run()
