"""Kiểm thử API pipeline, nhật ký chạy và các tình huống lỗi."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import PipelineRun, SessionLocal, ensure_ops_schema, schema_ready
from app.jobrunner import ActiveJob, runner
from app.main import app
from pipeline import quality as Q
from pipeline.runlog import tracked

pytestmark = pytest.mark.skipif(not schema_ready(), reason="Chưa tạo lược đồ")
client = TestClient(app)


def test_overview_lists_steps_and_counts():
    d = client.get("/api/pipeline/overview").json()
    assert [s["job"] for s in d["steps"]][:2] == ["etl", "quality"]
    assert d["counts"]["jobs"] > 0
    assert {j["job"] for j in d["jobs_available"]} == {"quality", "spark"}


def test_reconcile_has_no_mismatch():
    d = client.post("/api/pipeline/reconcile").json()
    bad = [c for c in d["checks"] if c["status"] == "fail"]
    assert not bad, bad
    assert d["summary"]["pass"] >= 10


def test_unknown_job_is_rejected():
    assert client.post("/api/pipeline/jobs", json={"job": "rm -rf /"}).status_code == 422


def test_second_job_is_refused_while_one_runs():
    runner.current = ActiveJob("quality")
    try:
        r = client.post("/api/pipeline/jobs", json={"job": "quality"})
        assert r.status_code == 409 and "Đang chạy" in r.json()["detail"]
    finally:
        runner.current = None


def test_tracked_records_success_and_failure():
    ensure_ops_schema()

    @tracked("test_ok", lambda r: {"rows_in": 3, "rows_out": r})
    def ok():
        return 2

    @tracked("test_bad")
    def bad():
        raise ValueError("hỏng")

    assert ok() == 2
    with pytest.raises(ValueError):
        bad()
    with SessionLocal() as db:
        rows = {r.job: r for r in db.scalars(select(PipelineRun).where(PipelineRun.job.in_(["test_ok", "test_bad"]))).all()}
        assert rows["test_ok"].status == "success" and rows["test_ok"].rows_out == 2
        assert rows["test_bad"].status == "failed" and "hỏng" in rows["test_bad"].detail["error"]
        for r in rows.values():
            db.delete(r)
        db.commit()


def test_quality_profile_measures_raw_data():
    raw = pd.DataFrame({
        "job_title": ["A", "A", "B", None], "location": ["x", "x", "y", "z"], "description": ["d", "d", "e", "f"],
        "salary_min": [10, 10, 0, 200], "salary_max": [20, 20, 0, 400],
    })
    p = Q.profile_raw(raw)
    assert p["rows"] == 4
    assert p["duplicates"] == {"full_row": 1, "same_posting": 1, "unique_postings": 3}
    assert p["salary"]["negotiable_rows"] == 1
    assert p["salary"]["above_range"] == 1
    assert next(c for c in p["columns_profile"] if c["name"] == "job_title")["missing"] == 1


def test_api_paths_never_fall_back_to_html():
    r = client.get("/api/khong-co-duong-dan-nay")
    assert r.status_code == 404 and "json" in r.headers["content-type"]


def test_static_route_cannot_escape_dist():
    r = client.get("/..%2f..%2fbackend%2frequirements.txt")
    assert "fastapi" not in r.text


def test_jobs_rejects_inverted_salary_range():
    assert client.get("/api/jobs", params={"min_salary": 30, "max_salary": 10}).status_code == 422


def test_jobs_search_ignores_accents():
    a = client.get("/api/jobs", params={"q": "ke toan", "size": 1}).json()["total"]
    b = client.get("/api/jobs", params={"q": "Kế Toán", "size": 1}).json()["total"]
    assert a == b > 0


def test_missing_job_is_404():
    assert client.get("/api/jobs/999999999").status_code == 404


def test_predict_validates_input():
    assert client.post("/api/predict/salary", json={"title": "x"}).status_code == 422
    assert client.post("/api/predict/salary", json={"title": "Kế toán", "experience_years": -1}).status_code == 422


def test_spark_watchdog_stops_a_hung_process(tmp_path, monkeypatch):
    """Job treo phải bị dừng đúng hạn, không được treo theo cả hệ thống."""
    import sys
    import time

    from pipeline import spark_job

    monkeypatch.setattr(spark_job, "WORK", tmp_path)
    t0 = time.time()
    code, lines = spark_job._stream([sys.executable, "-c", "import time; print('bat dau', flush=True); time.sleep(60)"], 2)
    assert code == -1 and time.time() - t0 < 20
    assert "bat dau" in lines and "Quá thời hạn" in lines[-1]
