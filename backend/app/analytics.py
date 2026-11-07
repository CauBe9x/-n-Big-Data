"""Logic phân tích cho Dashboard: mọi chỉ số được tính bằng SQL trên PostgreSQL theo đúng bộ lọc người dùng chọn.

Quy ước thống kê (giống pipeline khai phá và Superset):
- Lương chỉ xét tin công bố và nằm trong [1, 150] triệu/tháng; tin "thoả thuận" được đếm vào số tin nhưng không vào lương.
- Một tin đa ngành được tính ở mọi ngành của nó, nên tổng theo ngành lớn hơn tổng số tin.
- Nhóm có dưới MIN_N tin có lương không hiển thị trung vị: mẫu quá nhỏ để so sánh.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

SAL_LO, SAL_HI = 1, 150
MIN_N = 10            # số tin có lương tối thiểu để công bố trung vị của một nhóm
MIN_SKILL_N = 15      # số tin có lương tối thiểu để tính chênh lệch lương của một kỹ năng
HIST_BIN, HIST_MAX = 2, 60

EXP_ORDER = ["Không yêu cầu", "Dưới 1 năm", "1-2 năm", "3-5 năm", "Trên 5 năm", "Không rõ"]
HEAT_EXP = ["Không yêu cầu", "Dưới 1 năm", "1-2 năm", "3-5 năm", "Trên 5 năm"]
REGIONS = ["Miền Bắc", "Miền Trung", "Miền Nam", "Khác"]


@dataclass(frozen=True)
class Filters:
    region: str | None = None
    province: str | None = None
    category: str | None = None
    experience: str | None = None
    contract_type: str | None = None

    @property
    def active(self) -> bool:
        return any((self.region, self.province, self.category, self.experience, self.contract_type))

    def where(self) -> tuple[str, dict]:
        conds, params = ["TRUE"], {}
        if self.region:
            conds.append("p.region = :region")
            params["region"] = self.region
        if self.province:
            conds.append("p.name = :province")
            params["province"] = self.province
        if self.experience:
            conds.append("j.experience_bucket = :experience")
            params["experience"] = self.experience
        if self.contract_type:
            conds.append("j.contract_type = :contract_type")
            params["contract_type"] = self.contract_type
        if self.category:
            conds.append("""j.job_id IN (SELECT jc.job_id FROM job_categories jc
                                         JOIN categories c ON c.category_id = jc.category_id WHERE c.slug = :category)""")
            params["category"] = self.category
        return " AND ".join(conds), params


def _base(f: Filters) -> tuple[str, dict]:
    """CTE `f`: các tin thoả bộ lọc; cột sal = lương hợp lệ để tính thống kê."""
    where, params = f.where()
    return f"""WITH f AS MATERIALIZED (
        SELECT j.job_id, j.is_negotiable, j.experience_bucket, j.contract_type, p.name AS province, p.region,
               CASE WHEN j.salary_avg BETWEEN {SAL_LO} AND {SAL_HI} THEN j.salary_avg::float8 END AS sal
        FROM jobs j JOIN provinces p ON p.province_id = j.province_id
        WHERE {where})""", params


QUARTILES = "percentile_cont(ARRAY[0.25, 0.5, 0.75]::float8[]) WITHIN GROUP (ORDER BY sal)"


def _q(arr) -> dict:
    if not arr or arr[1] is None:
        return {"p25": None, "median": None, "p75": None}
    return {"p25": round(arr[0], 2), "median": round(arr[1], 2), "p75": round(arr[2], 2)}


def _guard(row: dict, n_salary: int) -> dict:
    """Ẩn thống kê lương của nhóm quá ít mẫu."""
    if n_salary < MIN_N:
        row.update(p25=None, median=None, p75=None)
    return row


def summary(db: Session, f: Filters) -> dict:
    base, params = _base(f)
    r = db.execute(text(f"""{base}
        SELECT count(*) AS n, count(sal) AS n_salary, count(*) FILTER (WHERE is_negotiable) AS n_negotiable,
               {QUARTILES} AS q, avg(sal) AS mean,
               count(*) FILTER (WHERE job_id IN (SELECT job_id FROM job_languages)) AS n_language
        FROM f"""), params).mappings().one()
    n = r["n"]
    return {"jobs": n, "with_salary": r["n_salary"], **_q(r["q"]),
            "mean": round(r["mean"], 2) if r["mean"] is not None else None,
            "negotiable_pct": round(r["n_negotiable"] * 100 / n, 1) if n else None,
            "language_pct": round(r["n_language"] * 100 / n, 1) if n else None}


def histogram(db: Session, f: Filters) -> list[dict]:
    base, params = _base(f)
    rows = dict(db.execute(text(f"""{base}
        SELECT least(floor(sal / {HIST_BIN})::int * {HIST_BIN}, {HIST_MAX}) AS bin, count(*) FROM f
        WHERE sal IS NOT NULL GROUP BY 1"""), params).all())
    out = []
    for lo in range(0, HIST_MAX + HIST_BIN, HIST_BIN):
        last = lo == HIST_MAX
        out.append({"from": lo, "to": None if last else lo + HIST_BIN, "range": f"{lo}+" if last else f"{lo}–{lo + HIST_BIN}",
                    "count": rows.get(lo, 0)})
    return out


def by_experience(db: Session, f: Filters) -> list[dict]:
    base, params = _base(f)
    rows = db.execute(text(f"""{base}
        SELECT experience_bucket AS bucket, count(*) AS n, count(sal) AS n_salary, {QUARTILES} AS q
        FROM f GROUP BY 1"""), params).mappings().all()
    data = {r["bucket"]: r for r in rows}
    return [_guard({"bucket": b, "jobs": data[b]["n"], "with_salary": data[b]["n_salary"], **_q(data[b]["q"])},
                   data[b]["n_salary"]) for b in EXP_ORDER if b in data]


def by_category(db: Session, f: Filters) -> list[dict]:
    """Bỏ riêng bộ lọc ngành khi vẽ bảng ngành: người xem luôn so được ngành đang chọn với các ngành khác."""
    base, params = _base(Filters(f.region, f.province, None, f.experience, f.contract_type))
    rows = db.execute(text(f"""{base}
        SELECT c.slug, c.name, count(*) AS n, count(f.sal) AS n_salary,
               count(*) FILTER (WHERE f.is_negotiable) AS n_neg, {QUARTILES} AS q
        FROM f JOIN job_categories jc ON jc.job_id = f.job_id JOIN categories c ON c.category_id = jc.category_id
        GROUP BY c.slug, c.name ORDER BY n DESC"""), params).mappings().all()
    return [_guard({"slug": r["slug"], "name": r["name"], "jobs": r["n"], "with_salary": r["n_salary"],
                    "negotiable_pct": round(r["n_neg"] * 100 / r["n"], 1), **_q(r["q"])}, r["n_salary"]) for r in rows]


def by_region(db: Session, f: Filters) -> list[dict]:
    base, params = _base(Filters(None, None, f.category, f.experience, f.contract_type))
    rows = db.execute(text(f"""{base}
        SELECT region, count(*) AS n, count(sal) AS n_salary, {QUARTILES} AS q FROM f GROUP BY 1"""),
                      params).mappings().all()
    data = {r["region"]: r for r in rows}
    return [_guard({"region": k, "jobs": data[k]["n"], "with_salary": data[k]["n_salary"], **_q(data[k]["q"])},
                   data[k]["n_salary"]) for k in REGIONS if k in data]


def by_province(db: Session, f: Filters, limit: int = 12) -> list[dict]:
    base, params = _base(Filters(f.region, None, f.category, f.experience, f.contract_type))
    rows = db.execute(text(f"""{base}
        SELECT province, region, count(*) AS n, count(sal) AS n_salary, {QUARTILES} AS q
        FROM f GROUP BY 1, 2 ORDER BY n DESC LIMIT :limit"""), {**params, "limit": limit}).mappings().all()
    return [_guard({"province": r["province"], "region": r["region"], "jobs": r["n"], "with_salary": r["n_salary"],
                    **_q(r["q"])}, r["n_salary"]) for r in rows]


def heatmap(db: Session, f: Filters) -> dict:
    """Lương trung vị theo ngành × kinh nghiệm. Ô dưới MIN_N tin có lương được để trống, không ước lượng."""
    base, params = _base(Filters(f.region, f.province, None, None, f.contract_type))
    rows = db.execute(text(f"""{base}
        SELECT c.name AS category, c.slug, f.experience_bucket AS exp, count(f.sal) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.sal) AS median
        FROM f JOIN job_categories jc ON jc.job_id = f.job_id JOIN categories c ON c.category_id = jc.category_id
        WHERE f.sal IS NOT NULL AND f.experience_bucket <> 'Không rõ'
        GROUP BY 1, 2, 3"""), params).mappings().all()
    cells: dict[str, dict] = {}
    for r in rows:
        row = cells.setdefault(r["slug"], {"slug": r["slug"], "category": r["category"], "cells": {}, "total": 0})
        row["cells"][r["exp"]] = {"median": round(r["median"], 1) if r["n"] >= MIN_N else None, "n": r["n"]}
        row["total"] += r["n"]
    return {"columns": HEAT_EXP, "min_n": MIN_N, "rows": sorted(cells.values(), key=lambda x: -x["total"])}


def skills(db: Session, f: Filters, kind: str = "technical", limit: int = 15) -> list[dict]:
    """Kỹ năng được yêu cầu nhiều nhất và chênh lệch lương trung vị so với nhóm tin đang lọc (tương quan, không phải nhân quả)."""
    base, params = _base(f)
    rows = db.execute(text(f"""{base},
        top AS (SELECT js.skill_id, count(*) AS n FROM f JOIN job_skills js ON js.job_id = f.job_id
                JOIN skills s ON s.skill_id = js.skill_id AND s.kind = :kind
                GROUP BY js.skill_id ORDER BY n DESC LIMIT :limit)
        SELECT s.name, t.n, count(f.sal) AS n_salary,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.sal) AS median
        FROM top t JOIN skills s ON s.skill_id = t.skill_id
        JOIN job_skills js ON js.skill_id = t.skill_id JOIN f ON f.job_id = js.job_id
        GROUP BY s.name, t.n ORDER BY t.n DESC"""), {**params, "kind": kind, "limit": limit}).mappings().all()
    total = db.execute(text(f"{base} SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY sal) FROM f"),
                       params).one()
    n_jobs, overall = total[0] or 1, total[1]
    out = []
    for r in rows:
        ok = r["n_salary"] >= MIN_SKILL_N and overall
        out.append({"skill": r["name"], "jobs": r["n"], "share_pct": round(r["n"] * 100 / n_jobs, 1),
                    "with_salary": r["n_salary"], "median": round(r["median"], 1) if ok else None,
                    "premium_pct": round((r["median"] / overall - 1) * 100, 1) if ok else None})
    return out


def languages(db: Session, f: Filters) -> list[dict]:
    base, params = _base(f)
    rows = db.execute(text(f"""{base}
        SELECT coalesce(l.name, 'Không yêu cầu ngoại ngữ') AS language, count(*) AS n, count(f.sal) AS n_salary, {QUARTILES} AS q
        FROM f LEFT JOIN job_languages jl ON jl.job_id = f.job_id LEFT JOIN languages l ON l.language_id = jl.language_id
        GROUP BY 1 ORDER BY n DESC LIMIT 7"""), params).mappings().all()
    return [_guard({"language": r["language"], "jobs": r["n"], "with_salary": r["n_salary"], **_q(r["q"])}, r["n_salary"])
            for r in rows]


def contracts(db: Session, f: Filters) -> list[dict]:
    base, params = _base(Filters(f.region, f.province, f.category, f.experience, None))
    rows = db.execute(text(f"""{base}
        SELECT contract_type, count(*) AS n, count(sal) AS n_salary, {QUARTILES} AS q
        FROM f GROUP BY 1 ORDER BY n DESC LIMIT 6"""), params).mappings().all()
    return [_guard({"contract_type": r["contract_type"], "jobs": r["n"], "with_salary": r["n_salary"], **_q(r["q"])},
                   r["n_salary"]) for r in rows]


def _pct(a: float, b: float) -> str:
    return f"{abs(a / b - 1) * 100:.0f}%".replace(".", ",")


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def insights(kpi: dict, market: dict, cats: list[dict], exp: list[dict], provs: list[dict], tech: list[dict],
             f: Filters) -> list[dict]:
    """Nhận định sinh tự động từ chính số liệu đang hiển thị; không đủ mẫu thì không nói."""
    out = []
    if f.active and kpi["median"] and market["median"]:
        diff = kpi["median"] - market["median"]
        word = "cao hơn" if diff > 0 else "thấp hơn"
        if abs(diff) >= 0.05:
            out.append({"title": "So với toàn thị trường",
                        "text": f"Nhóm đang lọc có lương trung vị {_num(kpi['median'])} triệu, {word} "
                                f"{_pct(kpi['median'], market['median'])} so với mức {_num(market['median'])} triệu của toàn bộ dữ liệu."})
    # "Nhóm nghề khác" là nhóm thu gom, so sánh với nó không nói lên điều gì
    ranked = [c for c in cats if c["median"] is not None and c["with_salary"] >= 30 and c["name"] != "Nhóm nghề khác"]
    if len(ranked) >= 2 and not f.category:
        top, bottom = max(c["median"] for c in ranked), min(c["median"] for c in ranked)
        if top > bottom:
            tops = [c["name"] for c in ranked if c["median"] == top]
            lows = [c["name"] for c in ranked if c["median"] == bottom]
            out.append({"title": "Chênh lệch giữa các ngành",
                        "text": f"{' và '.join(tops[:2])} có lương trung vị cao nhất ({_num(top)} triệu), hơn "
                                f"{_pct(top, bottom)} so với {' và '.join(lows[:2])} ({_num(bottom)} triệu)."})
    ex = {e["bucket"]: e for e in exp}
    a, b = ex.get("1-2 năm"), ex.get("3-5 năm")
    if a and b and a["median"] and b["median"] and a["median"] != b["median"]:
        word = "tăng" if b["median"] > a["median"] else "giảm"
        out.append({"title": "Bước nhảy kinh nghiệm",
                    "text": f"Từ nhóm 1-2 năm lên 3-5 năm, lương trung vị {word} {_pct(b['median'], a['median'])} "
                            f"({_num(a['median'])} → {_num(b['median'])} triệu)."})
    hidden = [c for c in cats if c["jobs"] >= 50 and c["name"] != "Nhóm nghề khác"]
    if hidden and not f.category:
        h = max(hidden, key=lambda c: c["negotiable_pct"])
        out.append({"title": "Nơi lương ít được công khai",
                    "text": f"{h['name']} có {_num(h['negotiable_pct'])}% tin ghi “thoả thuận”, nhiều nhất trong các ngành, "
                            f"nên số liệu lương của ngành này kém đại diện hơn."})
    prem = [t for t in tech if t["premium_pct"] is not None and t["with_salary"] >= 30]
    if prem:
        p = max(prem, key=lambda t: t["premium_pct"])
        if p["premium_pct"] > 0:
            out.append({"title": "Kỹ năng đi kèm lương cao",
                        "text": f"Trong các kỹ năng phổ biến, tin yêu cầu “{p['skill']}” có lương trung vị cao hơn nhóm đang xem "
                                f"{_num(p['premium_pct'])}%. Đây là tương quan, không chứng minh kỹ năng này làm tăng lương."})
    return out[:4]


_CACHE: dict[Filters, tuple[float, dict]] = {}
CACHE_SECONDS = 600
CACHE_MAX = 256


def dashboard(db: Session, f: Filters) -> dict:
    """Có cache theo bộ lọc: dữ liệu chỉ đổi khi chạy lại ETL, còn mỗi lần tính cần khoảng chục truy vấn gom nhóm."""
    hit = _CACHE.get(f)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    data = _compute(db, f)
    if len(_CACHE) >= CACHE_MAX:
        _CACHE.clear()
    _CACHE[f] = (time.time(), data)
    return data


def _compute(db: Session, f: Filters) -> dict:
    kpi = summary(db, f)
    market = summary(db, Filters()) if f.active else kpi
    cats = by_category(db, f)
    exp = by_experience(db, f)
    provs = by_province(db, f)
    tech = skills(db, f, "technical")
    return {
        "filters": {k: v for k, v in vars(f).items() if v},
        "rules": {"salary_range": [SAL_LO, SAL_HI], "min_group_n": MIN_N, "min_skill_n": MIN_SKILL_N},
        "kpi": kpi, "market": market,
        "histogram": histogram(db, f),
        "experience": exp,
        "categories": cats,
        "regions": by_region(db, f),
        "provinces": provs,
        "heatmap": heatmap(db, f),
        "skills": {"technical": tech, "soft": skills(db, f, "soft", 10)},
        "languages": languages(db, f),
        "contracts": contracts(db, f),
        "insights": insights(kpi, market, cats, exp, provs, tech, f),
    }
