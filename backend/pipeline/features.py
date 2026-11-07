"""Đặc trưng dùng chung cho huấn luyện & suy luận (backend import lại module này)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from .cleaning import experience_bucket


def split_pipe(text: str) -> list[str]:
    """Tokenizer cho chuỗi 'a|b|c' (danh sách kỹ năng/ngôn ngữ). Định nghĩa ở mức module để pickle được."""
    return [t for t in text.split("|") if t]


# Từ chung chung trong chức danh – loại khi phân cụm / đặt nhãn cụm
TITLE_STOPWORDS = [
    "nhân", "viên", "chuyên", "nhân viên", "chuyên viên", "trưởng", "phó", "thực", "tập", "sinh", "và", "các", "có",
    "không", "cho", "tại", "từ", "năm", "tháng", "kinh", "nghiệm", "kinh nghiệm", "thu", "nhập", "thu nhập", "lương",
    "triệu", "đi", "làm", "ngay", "đi làm", "làm ngay", "hấp", "dẫn", "hấp dẫn", "upto", "up", "to", "lên", "đến",
    "tới", "trên", "dưới", "với", "của", "the", "and", "of", "for", "in", "nam", "nữ", "khu", "vực", "hcm", "hn",
    "hà", "nội", "hồ", "chí", "minh", "tp", "fulltime", "parttime", "full", "time", "part", "gấp", "tuyển", "dụng",
    "cần", "người", "mới", "ra", "trường", "ưu", "tiên", "biết", "cao", "tốt", "về", "hỗ", "trợ",
]


def to_sorted_csr(X):
    """Chuẩn hoá ma trận thưa (CSR, chỉ số đã sắp xếp) để huấn luyện song song bằng joblib không lỗi."""
    X = X.tocsr().copy()
    X.sort_indices()
    return X


def clean_title(text: str) -> str:
    """Bỏ phần quảng cáo trong tiêu đề: 'Kế Toán - Thu Nhập 15 Triệu' -> 'kế toán thu nhập triệu'."""
    text = str(text or "").lower()
    text = re.sub(r"\d+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Dự đoán lương
# ---------------------------------------------------------------------------

SALARY_COLUMNS = ["title", "province", "contract_type", "category", "exp_bucket", "exp_years", "skills", "langs"]

FEATURE_GROUP_LABELS = {
    "title_word": "Chức danh (từ)",
    "title_char": "Chức danh (ký tự)",
    "province": "Địa điểm",
    "contract_type": "Loại hợp đồng",
    "category": "Ngành nghề",
    "exp_bucket": "Kinh nghiệm",
    "exp_years": "Kinh nghiệm",
    "skills": "Kỹ năng",
    "langs": "Ngoại ngữ",
}


def salary_frame(records: list[dict] | pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hoá đầu vào (từ bảng sạch hoặc từ API) về DataFrame cho mô hình lương."""
    if isinstance(records, pd.DataFrame):
        df = records
        out = pd.DataFrame({
            "title": df["title"].map(clean_title),
            "province": df["province"].astype(str),
            "contract_type": df["contract_type"].astype(str),
            # tin có thể thuộc nhiều ngành -> mã hoá multi-hot "a|b"
            "category": (df["category_slugs"].map(lambda l: "|".join(l)) if "category_slugs" in df
                         else df["category_slug"].astype(str)),
            "exp_years": pd.to_numeric(df["experience_years"], errors="coerce"),
            "skills": [ "|".join(list(a) + list(b)) for a, b in zip(df["tech_skills"], df["soft_skill_list"])],
            "langs": df["language_list"].map(lambda l: "|".join(l)),
        })
    else:
        out = pd.DataFrame({
            "title": [clean_title(r.get("title", "")) for r in records],
            "province": [str(r.get("province") or "Khác") for r in records],
            "contract_type": [str(r.get("contract_type") or "Toàn thời gian") for r in records],
            "category": [str(r.get("category") or "") for r in records],
            "exp_years": [np.nan if r.get("experience_years") is None else float(r["experience_years"]) for r in records],
            "skills": ["|".join(s.lower().strip() for s in (r.get("skills") or [])) for r in records],
            "langs": ["|".join(s.lower().strip() for s in (r.get("languages") or [])) for r in records],
        })
    out["exp_bucket"] = out["exp_years"].map(lambda v: experience_bucket(None if pd.isna(v) else v))
    return out[SALARY_COLUMNS]


# Các trường mà bài báo VietJobs dùng cho bài toán lương (để so sánh công bằng)
PAPER_SALARY_BLOCKS = ("title_word", "title_char", "province", "contract_type", "exp_bucket", "exp_years")


def salary_preprocessor(blocks: tuple[str, ...] | None = None) -> ColumnTransformer:
    ohe = dict(handle_unknown="infrequent_if_exist", min_frequency=10)
    all_blocks = [
        ("title_word", TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=40000, sublinear_tf=True), "title"),
        ("title_char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=5, max_features=30000,
                                       sublinear_tf=True), "title"),
        ("province", OneHotEncoder(**ohe), ["province"]),
        ("contract_type", OneHotEncoder(**ohe), ["contract_type"]),
        ("category", CountVectorizer(tokenizer=split_pipe, token_pattern=None, lowercase=False, binary=True), "category"),
        ("exp_bucket", OneHotEncoder(**ohe), ["exp_bucket"]),
        ("exp_years", make_pipeline(SimpleImputer(strategy="median")), ["exp_years"]),
        ("skills", CountVectorizer(tokenizer=split_pipe, token_pattern=None, lowercase=False, binary=True, min_df=5), "skills"),
        ("langs", CountVectorizer(tokenizer=split_pipe, token_pattern=None, lowercase=False, binary=True, min_df=3), "langs"),
    ]
    if blocks:
        all_blocks = [b for b in all_blocks if b[0] in blocks]
    return ColumnTransformer(all_blocks, sparse_threshold=1.0)


# ---------------------------------------------------------------------------
# Phân loại ngành & gợi ý kỹ năng (văn bản)
# ---------------------------------------------------------------------------

def job_text(title: str, description: str | None = None, requirements: str | None = None, max_len: int = 3000) -> str:
    parts = [str(title or "")] * 2 + [str(description or ""), str(requirements or "")]
    text = " . ".join(p for p in parts if p and p.lower() != "nan")
    return text[:max_len]


def text_frame(titles, descriptions=None) -> pd.DataFrame:
    titles = [clean_title(t) for t in titles]
    if descriptions is None:
        descriptions = [""] * len(titles)
    descriptions = ["" if (d is None or (isinstance(d, float) and np.isnan(d))) else str(d)[:3000] for d in descriptions]
    return pd.DataFrame({"title": titles, "desc": descriptions})


def text_preprocessor(use_title: bool = True, use_desc: bool = True) -> ColumnTransformer:
    """Tiêu đề và mô tả được vector hoá riêng -> chỉ nhập tiêu đề vẫn dự đoán được."""
    blocks = []
    if not use_desc:
        return ColumnTransformer([
            ("title_word", TfidfVectorizer(ngram_range=(1, 3), min_df=2, max_features=60000, sublinear_tf=True), "title"),
            ("title_char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, max_features=60000,
                                           sublinear_tf=True), "title"),
        ], sparse_threshold=1.0)
    if use_title:
        blocks += [
            ("title_word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=40000, sublinear_tf=True), "title"),
            ("title_char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=30000,
                                           sublinear_tf=True), "title"),
        ]
    blocks.append(("desc_word", TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.6, max_features=80000,
                                                sublinear_tf=True), "desc"))
    return ColumnTransformer(blocks, sparse_threshold=1.0)
