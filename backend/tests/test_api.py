"""Kiểm thử nhanh API (cần chạy pipeline trước để có CSDL và mô hình)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from pipeline.inference import models_status

client = TestClient(app)
ready = all(models_status().values())


def test_health():
    assert client.get("/api/health").status_code == 200


@pytest.mark.skipif(not ready, reason="Chưa huấn luyện mô hình")
@pytest.mark.parametrize("url", ["/api/meta", "/api/stats/overview", "/api/stats/categories", "/api/stats/experience",
                                 "/api/stats/top-skills", "/api/jobs?q=ke toan", "/api/mining/rules",
                                 "/api/mining/clusters", "/api/mining/skill-value", "/api/models/reports"])
def test_get_endpoints(url):
    assert client.get(url).status_code == 200


@pytest.mark.skipif(not ready, reason="Chưa huấn luyện mô hình")
def test_predictions():
    r = client.post("/api/predict/salary", json={"title": "Kế toán tổng hợp", "province": "Hà Nội", "experience_years": 2})
    assert r.status_code == 200 and r.json()["low"] <= r.json()["predicted"] <= r.json()["high"]
    assert client.post("/api/predict/skills", json={"title": "Data Analyst"}).status_code == 200
    assert client.post("/api/predict/category", json={"title": "Dược sĩ"}).status_code == 200
