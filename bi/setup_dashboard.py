"""Dựng tự động dashboard EDA trên Apache Superset qua REST API.

Tạo: kết nối CSDL PostgreSQL 'vietjobs' -> các dataset (view v_job_*) -> các biểu đồ -> dashboard 'VietJobs'.
Chạy lại nhiều lần được (xoá & tạo lại các đối tượng cùng tên).

    python bi/setup_dashboard.py
    # tuỳ chọn:
    SUPERSET_URL=http://localhost:8088 SUPERSET_USER=admin SUPERSET_PASSWORD=admin \
    VIETJOBS_DB_URI=postgresql+psycopg2://vietjobs:vietjobs@postgres:5432/vietjobs python bi/setup_dashboard.py

(Khi Superset chạy trong Docker, host của PostgreSQL là tên service 'postgres' thay vì 'localhost'.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = os.getenv("SUPERSET_URL", "http://localhost:8088").rstrip("/")
USER = os.getenv("SUPERSET_USER", "admin")
PASSWORD = os.getenv("SUPERSET_PASSWORD", "admin")
DB_URI = os.getenv("VIETJOBS_DB_URI", "postgresql+psycopg2://vietjobs:vietjobs@localhost:5432/vietjobs")
DB_NAME = "VietJobs PostgreSQL"
DASH_TITLE = "VietJobs – Thị trường tuyển dụng"
DASH_SLUG = "vietjobs"

MEDIAN = {"expressionType": "SQL", "label": "Lương trung vị (triệu)",
          "sqlExpression": "ROUND(CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_valid) AS numeric), 1)"}
COUNT = {"expressionType": "SQL", "label": "Số tin", "sqlExpression": "COUNT(*)"}
COUNT_JOBS = {"expressionType": "SQL", "label": "Số tin", "sqlExpression": "COUNT(DISTINCT job_id)"}
HAS_SALARY = {"expressionType": "SIMPLE", "subject": "salary_valid", "operator": "IS NOT NULL", "clause": "WHERE"}


# ----------------------------------------------------------------------------- HTTP
class Api:
    def __init__(self) -> None:
        self.token = None
        data = self.call("POST", "/api/v1/security/login",
                         {"username": USER, "password": PASSWORD, "provider": "db", "refresh": True})
        self.token = data["access_token"]

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(URL + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:600]}") from e

    def find(self, resource: str, col: str, value: str) -> list[int]:
        value = value.replace("!", "!!").replace("'", "!'")   # thoát ký tự theo cú pháp rison
        q = f"(filters:!((col:{col},opr:eq,value:'{value}')),page_size:100)"
        return [r["id"] for r in self.call("GET", f"/api/v1/{resource}/?q={urllib.parse.quote(q)}").get("result", [])]


# ----------------------------------------------------------------------------- dựng đối tượng
def ensure_database(api: Api) -> int:
    for i in api.find("database", "database_name", DB_NAME):
        return api.call("PUT", f"/api/v1/database/{i}", {"sqlalchemy_uri": DB_URI, "expose_in_sqllab": True})["id"]
    return api.call("POST", "/api/v1/database/", {"database_name": DB_NAME, "sqlalchemy_uri": DB_URI,
                                                   "expose_in_sqllab": True})["id"]


def ensure_dataset(api: Api, db_id: int, table: str, sql: str | None = None) -> int:
    for i in api.find("dataset", "table_name", table):
        api.call("DELETE", f"/api/v1/dataset/{i}")
    body = {"database": db_id, "schema": "public", "table_name": table}
    if sql:
        body["sql"] = sql
    return api.call("POST", "/api/v1/dataset/", body)["id"]


def chart(api: Api, name: str, ds: int, viz: str, params: dict) -> int:
    for i in api.find("chart", "slice_name", name):
        api.call("DELETE", f"/api/v1/chart/{i}")
    params = {"viz_type": viz, "datasource": f"{ds}__table", **params}
    return api.call("POST", "/api/v1/chart/", {"slice_name": name, "viz_type": viz, "datasource_id": ds,
                                                "datasource_type": "table", "params": json.dumps(params)})["id"]


def bar(x: str, metric: dict, *, horizontal: bool = True, limit: int = 20, filters=(), sort_by_metric=True,
        y_title: str = "", x_title: str = "") -> dict:
    p = {"x_axis": x, "metrics": [metric], "groupby": [], "adhoc_filters": list(filters), "row_limit": limit,
         "orientation": "horizontal" if horizontal else "vertical", "show_value": True, "show_legend": False,
         "rich_tooltip": True, "y_axis_format": "SMART_NUMBER", "color_scheme": "supersetColors",
         "x_axis_title": x_title, "y_axis_title": y_title, "truncateXAxis": True, "xAxisLabelRotation": 0}
    if sort_by_metric:
        p.update({"x_axis_sort": metric["label"], "x_axis_sort_asc": horizontal})
    return p


def build(api: Api) -> None:
    db = ensure_database(api)
    print(f"  - Kết nối CSDL '{DB_NAME}' (id={db})")
    facts = ensure_dataset(api, db, "v_job_facts")
    jcat = ensure_dataset(api, db, "v_job_categories")
    jskill = ensure_dataset(api, db, "v_job_skills")
    models = ensure_dataset(api, db, "ds_model_test", sql="""
        SELECT CASE task WHEN 'salary' THEN '1. Dự đoán lương' WHEN 'skills' THEN '2. Gợi ý kỹ năng'
                         ELSE '3. Phân loại ngành' END AS "Bài toán",
               model AS "Mô hình", CASE WHEN is_best THEN 'triển khai' ELSE '' END AS " ",
               metric AS "Chỉ số", ROUND(CAST(value AS numeric), 3) AS "Giá trị"
        FROM v_model_results
        WHERE split = 'test' AND metric IN ('RMSE', 'R2', 'Accuracy', 'Macro_F1', 'Precision@5', 'Recall@10')""")
    rules = ensure_dataset(api, db, "ds_association_rules", sql="""
        SELECT r.rule_id, string_agg(s.name, ', ' ORDER BY s.name) AS "Nếu tin yêu cầu",
               r.consequent_label AS "Thì thường có", r.consequent_type AS loai,
               ROUND(CAST(r.support * 100 AS numeric), 2) AS "Độ hỗ trợ %",
               ROUND(CAST(r.confidence * 100 AS numeric), 1) AS "Độ tin cậy %", ROUND(CAST(r.lift AS numeric), 2) AS lift
        FROM association_rules r JOIN rule_antecedents a USING (rule_id) JOIN skills s USING (skill_id)
        GROUP BY r.rule_id""")
    clusters = ensure_dataset(api, db, "ds_clusters", sql="""
        SELECT label AS "Cụm công việc", size AS "Số tin", median_salary AS "Lương trung vị",
               (SELECT string_agg(x, ', ') FROM jsonb_array_elements_text(distinct_skills) AS x) AS "Kỹ năng đặc trưng"
        FROM clusters""")
    print("  - 6 dataset: v_job_facts, v_job_categories, v_job_skills, ds_model_test, ds_association_rules, ds_clusters")

    c = {}
    c["kpi_jobs"] = chart(api, "Số tin tuyển dụng", facts, "big_number_total",
                          {"metric": COUNT, "subheader": "tin duy nhất sau khi gộp trùng", "y_axis_format": ",d"})
    c["kpi_median"] = chart(api, "Lương trung vị", facts, "big_number_total",
                            {"metric": MEDIAN, "subheader": "triệu đồng/tháng", "y_axis_format": ".1f"})
    c["kpi_neg"] = chart(api, "Tỷ lệ tin 'thoả thuận'", facts, "big_number_total",
                         {"metric": {"expressionType": "SQL", "label": "% thoả thuận",
                                     "sqlExpression": "AVG(CASE WHEN is_negotiable THEN 1.0 ELSE 0 END)"},
                          "subheader": "không công khai mức lương", "y_axis_format": ".1%"})
    c["kpi_lang"] = chart(api, "Tin yêu cầu ngoại ngữ", facts, "big_number_total",
                          {"metric": {"expressionType": "SQL", "label": "% ngoại ngữ",
                                      "sqlExpression": "AVG(CASE WHEN requires_language THEN 1.0 ELSE 0 END)"},
                           "subheader": "trên tổng số tin", "y_axis_format": ".1%"})
    c["hist"] = chart(api, "Phân bố mức lương (triệu/tháng)", facts, "histogram_v2",
                      {"column": "salary_valid", "groupby": [], "bins": 30, "adhoc_filters": [
                          {"expressionType": "SQL", "sqlExpression": "salary_valid <= 80", "clause": "WHERE"}],
                       "x_axis_title": "Lương (triệu)", "y_axis_title": "Số tin", "row_limit": 50000,
                       "show_legend": False, "color_scheme": "supersetColors"})
    c["exp"] = chart(api, "Lương trung vị theo kinh nghiệm", facts, "echarts_timeseries_bar",
                     {**bar("experience_level", MEDIAN, horizontal=False, filters=[HAS_SALARY], sort_by_metric=False),
                      "x_axis_sort": "experience_level", "x_axis_sort_asc": True})
    c["cat_count"] = chart(api, "Số tin theo ngành", jcat, "echarts_timeseries_bar", bar("category", COUNT_JOBS))
    c["cat_salary"] = chart(api, "Lương trung vị theo ngành", jcat, "echarts_timeseries_bar",
                            bar("category", MEDIAN, filters=[HAS_SALARY]))
    c["prov"] = chart(api, "Top 15 tỉnh/thành theo số tin", facts, "echarts_timeseries_bar",
                      bar("province", COUNT, limit=15))
    c["region"] = chart(api, "Tỷ trọng tin theo miền", facts, "pie",
                        {"groupby": ["region"], "metric": COUNT, "show_labels": True, "label_type": "percent",
                         "labels_outside": False, "donut": True, "show_legend": True, "legendOrientation": "bottom", "row_limit": 10, "color_scheme": "supersetColors"})
    c["tech"] = chart(api, "Top 20 kỹ năng chuyên môn", jskill, "echarts_timeseries_bar",
                      bar("skill", COUNT, filters=[{"expressionType": "SIMPLE", "subject": "kind", "operator": "==",
                                                    "comparator": "technical", "clause": "WHERE"}]))
    c["soft"] = chart(api, "Top 20 kỹ năng mềm", jskill, "echarts_timeseries_bar",
                      bar("skill", COUNT, filters=[{"expressionType": "SIMPLE", "subject": "kind", "operator": "==",
                                                    "comparator": "soft", "clause": "WHERE"}]))
    c["heat"] = chart(api, "Lương trung vị: ngành × kinh nghiệm (bỏ nhóm trên 5 năm vì quá ít tin)", jcat, "heatmap_v2",
                      {"x_axis": "experience_level", "groupby": "category", "metric": MEDIAN,
                       "row_limit": 1000, "linear_color_scheme": "blue_white_yellow",
                       "show_values": True, "normalize_across": "heatmap", "value_bounds": [None, None],
                       "adhoc_filters": [HAS_SALARY, {"expressionType": "SQL", "clause": "WHERE",
                                                      "sqlExpression": "experience_level <> '5. Trên 5 năm'"}],
                       "y_axis_format": ".1f", "sort_x_axis": "alpha_asc", "sort_y_axis": "alpha_asc",
                       "left_margin": "auto", "bottom_margin": "auto", "legend_type": "continuous"})
    c["models"] = chart(api, "Kết quả các mô hình trên tập test", models, "table",
                        {"query_mode": "raw", "all_columns": ["Bài toán", "Mô hình", " ", "Chỉ số", "Giá trị"],
                         "order_by_cols": ['["Bài toán", true]', '["Mô hình", true]', '["Chỉ số", true]'],
                         "row_limit": 200, "include_search": False, "page_length": 0, "show_cell_bars": False})
    c["rules"] = chart(api, "Luật kết hợp có lift cao nhất", rules, "table",
                       {"query_mode": "raw", "all_columns": ["Nếu tin yêu cầu", "Thì thường có", "Độ hỗ trợ %",
                                                             "Độ tin cậy %", "lift"],
                        "order_by_cols": ['["lift", false]'], "row_limit": 2000, "include_search": True,
                        "server_pagination": False, "page_length": 15})
    c["clusters"] = chart(api, "Các cụm công việc (K-Means)", clusters, "table",
                          {"query_mode": "raw", "all_columns": ["Cụm công việc", "Số tin", "Lương trung vị",
                                                                "Kỹ năng đặc trưng"],
                           "order_by_cols": ['["Số tin", false]'], "row_limit": 100, "include_search": True,
                           "page_length": 15})
    print(f"  - {len(c)} biểu đồ")

    # ------------------------------------------------------------- bố cục dashboard (lưới 12 cột)
    rows = [
        ("Tổng quan", [("kpi_jobs", 3, 24), ("kpi_median", 3, 24), ("kpi_neg", 3, 24), ("kpi_lang", 3, 24)]),
        (None, [("hist", 6, 60), ("exp", 6, 60)]),
        ("Ngành nghề", [("cat_count", 6, 90), ("cat_salary", 6, 90)]),
        (None, [("heat", 12, 90)]),
        ("Địa điểm", [("prov", 8, 70), ("region", 4, 70)]),
        ("Kỹ năng", [("tech", 6, 90), ("soft", 6, 90)]),
        ("Máy học & khai phá dữ liệu", [("models", 5, 110), ("clusters", 7, 110)]),
        (None, [("rules", 12, 100)]),
    ]
    pos = {"DASHBOARD_VERSION_KEY": "v2", "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASH_TITLE}}}
    for r_i, (header, items) in enumerate(rows):
        if header:
            hid = f"HEADER-{r_i}"
            pos[hid] = {"type": "HEADER", "id": hid, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                        "meta": {"text": header, "headerSize": "MEDIUM_HEADER", "background": "BACKGROUND_TRANSPARENT"}}
            pos["GRID_ID"]["children"].append(hid)
        rid = f"ROW-{r_i}"
        pos[rid] = {"type": "ROW", "id": rid, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        pos["GRID_ID"]["children"].append(rid)
        for key, width, height in items:
            cid = f"CHART-{key}"
            pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": ["ROOT_ID", "GRID_ID", rid],
                        "meta": {"chartId": c[key], "width": width, "height": height}}
            pos[rid]["children"].append(cid)

    # Bộ lọc dùng chung: miền, kinh nghiệm (áp dụng cho mọi biểu đồ có cột tương ứng)
    def native_filter(fid: str, name: str, column: str) -> dict:
        return {"id": fid, "name": name, "filterType": "filter_select", "type": "NATIVE_FILTER",
                "targets": [{"datasetId": facts, "column": {"name": column}}],
                "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "searchAllOptions": False,
                                  "inverseSelection": False, "defaultToFirstItem": False},
                "defaultDataMask": {"filterState": {}, "extraFormData": {}}, "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "chartsInScope": list(c.values()),
                "description": ""}

    meta = {"native_filter_configuration": [native_filter("NATIVE_FILTER-region", "Miền", "region"),
                                            native_filter("NATIVE_FILTER-exp", "Kinh nghiệm", "experience_level")],
            "color_scheme": "supersetColors", "refresh_frequency": 0, "cross_filters_enabled": True,
            "timed_refresh_immune_slices": [], "expanded_slices": {}, "label_colors": {}}

    for i in api.find("dashboard", "slug", DASH_SLUG):
        api.call("DELETE", f"/api/v1/dashboard/{i}")
    dash = api.call("POST", "/api/v1/dashboard/", {
        "dashboard_title": DASH_TITLE, "slug": DASH_SLUG, "published": True,
        "position_json": json.dumps(pos), "json_metadata": json.dumps(meta)})
    dash_id = dash["id"]
    for cid in c.values():   # gắn chart vào dashboard
        api.call("PUT", f"/api/v1/chart/{cid}", {"dashboards": [dash_id]})
    print(f"  - Dashboard: {URL}/superset/dashboard/{DASH_SLUG}/")


if __name__ == "__main__":
    print(f"[Superset] {URL}")
    try:
        build(Api())
    except urllib.error.URLError as exc:
        sys.exit(f"Không kết nối được Superset tại {URL}: {exc}")
    print("[Superset] Xong. Đăng nhập admin/admin rồi mở dashboard ở trên.")
