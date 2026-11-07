"""Kiểm thử API Dashboard trên dữ liệu thật (cần đã chạy pipeline)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import analytics as A
from app.db import engine, schema_ready
from app.main import app

pytestmark = pytest.mark.skipif(not schema_ready(), reason="Chưa tạo lược đồ")
client = TestClient(app)


def get(**params):
    r = client.get("/api/dashboard", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def scalar(sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_market_totals_match_database():
    d = get()
    assert d["kpi"]["jobs"] == scalar("SELECT count(*) FROM jobs")
    assert d["kpi"]["with_salary"] == scalar("SELECT count(*) FROM jobs WHERE salary_avg BETWEEN 1 AND 150")
    expected = scalar("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_avg)::float8 FROM jobs "
                      "WHERE salary_avg BETWEEN 1 AND 150")
    assert d["kpi"]["median"] == round(expected, 2)


def test_quartiles_are_ordered():
    k = get()["kpi"]
    assert k["p25"] <= k["median"] <= k["p75"]


def test_breakdowns_add_up():
    d = get()
    assert sum(b["count"] for b in d["histogram"]) == d["kpi"]["with_salary"]
    assert sum(e["jobs"] for e in d["experience"]) == d["kpi"]["jobs"]
    assert sum(r["jobs"] for r in d["regions"]) == d["kpi"]["jobs"]


def test_filter_narrows_and_keeps_market_reference():
    d = get(region="Miền Trung", experience="3-5 năm")
    assert 0 < d["kpi"]["jobs"] < d["market"]["jobs"]
    assert d["filters"] == {"region": "Miền Trung", "experience": "3-5 năm"}
    assert d["market"]["jobs"] == get()["kpi"]["jobs"]


def test_category_table_still_lists_every_category_when_filtered():
    slug = get()["categories"][0]["slug"]
    d = get(category=slug)
    assert len(d["categories"]) == len(get()["categories"])
    assert d["kpi"]["jobs"] == next(c["jobs"] for c in d["categories"] if c["slug"] == slug)


def test_small_groups_hide_median():
    for row in get()["heatmap"]["rows"]:
        for cell in row["cells"].values():
            assert (cell["median"] is None) == (cell["n"] < A.MIN_N)


@pytest.mark.parametrize("value", ["Tỉnh không tồn tại", "' OR 1=1 --"])
def test_unknown_or_hostile_province_returns_empty(value):
    d = get(province=value)
    assert d["kpi"]["jobs"] == 0 and d["kpi"]["median"] is None
    assert d["insights"] == []


@pytest.mark.parametrize("params", [{"region": "Sao Hoả"}, {"experience": "100 năm"}, {"province": "x" * 101}])
def test_invalid_filters_are_rejected(params):
    assert client.get("/api/dashboard", params=params).status_code == 422


def test_insights_cite_numbers_from_same_response():
    d = get()
    assert d["insights"], "toàn thị trường phải có nhận định"
    jump = next(i for i in d["insights"] if i["title"] == "Bước nhảy kinh nghiệm")
    exp = {e["bucket"]: e for e in d["experience"]}
    assert str(exp["3-5 năm"]["median"]).replace(".", ",") in jump["text"]
