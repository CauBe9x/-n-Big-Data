"""Đối soát dữ liệu: kiểm tra chéo CSV gốc, PostgreSQL, mô hình và kết quả Spark.

Mỗi kiểm tra trả về giá trị kỳ vọng, giá trị đo được và kết luận. Không kiểm tra nào được coi là đạt khi thiếu dữ liệu đầu vào:
trường hợp đó có trạng thái `skipped` và lý do.

Chạy: python -m pipeline.reconcile
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import ARTIFACTS_DIR, LAKE_DIR

SPARK_METRICS = LAKE_DIR / "spark_metrics.json"
MEDIAN_TOLERANCE = 0.5  # triệu: percentile_approx của Spark là xấp xỉ, percentile_cont của PostgreSQL là chính xác


def _check(group: str, name: str, expected, actual, ok: bool | None = None, note: str = "") -> dict:
    status = "pass" if (expected == actual if ok is None else ok) else "fail"
    return {"group": group, "name": name, "expected": expected, "actual": actual, "status": status, "note": note}


def _skip(group: str, name: str, reason: str) -> dict:
    return {"group": group, "name": name, "expected": None, "actual": None, "status": "skipped", "note": reason}


def _one(db: Session, sql: str):
    return db.execute(text(sql)).scalar()


def _latest_quality(db: Session) -> dict | None:
    return _one(db, "SELECT detail FROM pipeline_runs WHERE job = 'quality' AND status = 'success' "
                    "ORDER BY run_id DESC LIMIT 1")


def run_checks(db: Session) -> dict:
    checks: list[dict] = []
    jobs = _one(db, "SELECT count(*) FROM jobs")

    # --- CSV gốc <-> PostgreSQL
    quality = _latest_quality(db)
    if quality:
        raw = quality["raw"]
        checks.append(_check("Nguồn ↔ CSDL", "Tổng dòng CSV gộp vào các tin", raw["rows"],
                             int(_one(db, "SELECT sum(source_rows) FROM jobs")),
                             note="jobs.source_rows phải cộng lại đúng số dòng gốc: không mất, không thừa dòng"))
        checks.append(_check("Nguồn ↔ CSDL", "Số tin duy nhất", raw["duplicates"]["unique_postings"], jobs))
    else:
        checks.append(_skip("Nguồn ↔ CSDL", "Đối chiếu với CSV gốc", "Chưa chạy bước kiểm định chất lượng"))

    # --- Toàn vẹn dữ liệu
    checks.append(_check("Toàn vẹn", "Tin không có đúng 1 ngành chính", 0, _one(db, """
        SELECT count(*) FROM jobs j LEFT JOIN job_categories jc ON jc.job_id = j.job_id AND jc.is_primary
        WHERE jc.category_id IS DISTINCT FROM j.primary_category_id""")))
    checks.append(_check("Toàn vẹn", "Tin có salary_min > salary_max", 0,
                         _one(db, "SELECT count(*) FROM jobs WHERE salary_min > salary_max")))
    checks.append(_check("Toàn vẹn", "Tin thoả thuận khớp với lương rỗng",
                         _one(db, "SELECT count(*) FROM jobs WHERE salary_avg IS NULL"),
                         _one(db, "SELECT count(*) FROM jobs WHERE is_negotiable")))
    checks.append(_check("Toàn vẹn", "Liên kết kỹ năng trỏ tới tin không tồn tại", 0, _one(db, """
        SELECT count(*) FROM job_skills js LEFT JOIN jobs j ON j.job_id = js.job_id WHERE j.job_id IS NULL""")))
    checks.append(_check("Toàn vẹn", "Tin thuộc đúng một cụm K-Means", jobs, _one(db, "SELECT count(*) FROM job_clusters"),
                         note="Mỗi tin phải được gán đúng một cụm trong job_clusters"))

    # --- Tính nhất quán của phép thống kê: tính lại bằng hai cách độc lập
    from app import analytics as A
    market = A.summary(db, A.Filters())
    direct = _one(db, "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_avg)::float8 FROM jobs "
                      "WHERE salary_avg BETWEEN 1 AND 150")
    checks.append(_check("Thống kê", "Lương trung vị: API Dashboard ↔ truy vấn trực tiếp", round(direct, 2), market["median"]))
    view = _one(db, "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_valid)::float8 FROM v_job_facts")
    checks.append(_check("Thống kê", "Lương trung vị: API Dashboard ↔ view BI v_job_facts", round(view, 2), market["median"]))
    hist = sum(b["count"] for b in A.histogram(db, A.Filters()))
    checks.append(_check("Thống kê", "Tổng các cột histogram = số tin có lương hợp lệ", market["with_salary"], hist))
    exp = sum(e["jobs"] for e in A.by_experience(db, A.Filters()))
    checks.append(_check("Thống kê", "Tổng theo kinh nghiệm = tổng số tin", jobs, exp))
    region = sum(r["jobs"] for r in A.by_region(db, A.Filters()))
    checks.append(_check("Thống kê", "Tổng theo miền = tổng số tin", jobs, region))

    # --- Mô hình
    for task in ("salary", "skills", "category"):
        best = _one(db, f"""SELECT m.artifact_path FROM ml_models m JOIN ml_training_runs r USING (run_id)
                            WHERE r.task = '{task}' AND m.is_best ORDER BY r.run_id DESC LIMIT 1""")
        file = ARTIFACTS_DIR / f"{task}_model.joblib"
        if best is None:
            checks.append(_skip("Mô hình", f"Mô hình {task}", "Chưa có lần huấn luyện nào trong CSDL"))
        else:
            checks.append(_check("Mô hình", f"File mô hình {task} tồn tại và được đăng ký", True, file.exists(),
                                 note=best))

    # --- Spark <-> PostgreSQL: hai đường xử lý độc lập phải cho cùng kết quả
    if SPARK_METRICS.exists():
        sp = json.loads(SPARK_METRICS.read_text(encoding="utf-8"))
        rec = sp.get("reconcile", {})
        checks.append(_check("Spark ↔ CSDL", "Số tin sau khi gộp", jobs, rec.get("n_jobs")))
        checks.append(_check("Spark ↔ CSDL", "Số tin đa ngành",
                             _one(db, "SELECT count(*) FROM (SELECT job_id FROM job_categories GROUP BY 1 HAVING count(*) > 1) t"),
                             rec.get("n_multi_category")))
        checks.append(_check("Spark ↔ CSDL", "Số tin có lương hợp lệ", market["with_salary"], rec.get("n_salary")))
        checks.append(_check("Spark ↔ CSDL", "Số liên kết tin–kỹ năng",
                             _one(db, "SELECT count(*) FROM job_skills"), rec.get("n_skill_links")))
        for e in A.by_experience(db, A.Filters()):
            sm = rec.get("median_by_experience", {}).get(e["bucket"])
            if e["median"] is not None and sm is not None:
                checks.append(_check("Spark ↔ CSDL", f"Lương trung vị nhóm {e['bucket']}", e["median"], sm,
                                     ok=abs(e["median"] - sm) <= MEDIAN_TOLERANCE,
                                     note=f"Cho phép lệch {MEDIAN_TOLERANCE} triệu vì Spark dùng percentile_approx"))
    else:
        checks.append(_skip("Spark ↔ CSDL", "Đối chiếu với kết quả Spark", "Chưa chạy Spark pipeline"))

    counts = {s: sum(c["status"] == s for c in checks) for s in ("pass", "fail", "skipped")}
    return {"ok": counts["fail"] == 0, "summary": counts, "checks": checks}


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as session:
        res = run_checks(session)
    for c in res["checks"]:
        print(f"[{c['status']:7s}] {c['group']:14s} {c['name']}: kỳ vọng={c['expected']} thực tế={c['actual']}")
    print(res["summary"])
    raise SystemExit(0 if res["ok"] else 1)
