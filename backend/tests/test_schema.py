"""Kiểm tra lược đồ PostgreSQL (cần đã chạy: python -m pipeline.etl)."""
import pytest
from sqlalchemy import text

from app.db import engine, schema_ready

pytestmark = pytest.mark.skipif(not schema_ready(), reason="Chưa tạo lược đồ")

TABLES = {"provinces", "categories", "skills", "languages", "jobs", "job_categories", "job_skills", "job_languages",
          "ml_training_runs", "ml_models", "model_metrics", "predictions", "mining_runs", "association_rules",
          "rule_antecedents", "clusters", "job_clusters", "cluster_k_scores", "skill_salary_stats"}
VIEWS = {"v_job_facts", "v_job_categories", "v_job_skills", "v_model_results"}


def q(sql):
    with engine.connect() as c:
        return c.execute(text(sql)).all()


def test_tables_and_views():
    tables = {r[0] for r in q("SELECT table_name FROM information_schema.tables "
                              "WHERE table_schema='public' AND table_type='BASE TABLE'")}
    views = {r[0] for r in q("SELECT table_name FROM information_schema.views WHERE table_schema='public'")}
    assert TABLES <= tables
    assert VIEWS <= views


def test_every_table_has_primary_key():
    with_pk = {r[0] for r in q("SELECT table_name FROM information_schema.table_constraints "
                               "WHERE constraint_type='PRIMARY KEY' AND table_schema='public'")}
    assert TABLES <= with_pk


@pytest.mark.parametrize("child,col,parent", [
    ("jobs", "province_id", "provinces"), ("jobs", "primary_category_id", "categories"),
    ("job_categories", "job_id", "jobs"), ("job_categories", "category_id", "categories"),
    ("job_skills", "skill_id", "skills"), ("job_languages", "language_id", "languages"),
    ("ml_models", "run_id", "ml_training_runs"), ("model_metrics", "model_id", "ml_models"),
    ("predictions", "model_id", "ml_models"), ("rule_antecedents", "rule_id", "association_rules"),
    ("rule_antecedents", "skill_id", "skills"), ("job_clusters", "cluster_id", "clusters"),
])
def test_foreign_keys(child, col, parent):
    rows = q(f"""SELECT 1 FROM pg_constraint con
                 JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
                 WHERE con.contype = 'f' AND con.conrelid = '{child}'::regclass
                   AND con.confrelid = '{parent}'::regclass AND a.attname = '{col}'""")
    assert rows, f"thiếu khoá ngoại {child}.{col} -> {parent}"


def test_data_integrity():
    # mỗi tin có đúng 1 ngành chính trong bảng nối và khớp jobs.primary_category_id
    bad = q("""SELECT j.job_id FROM jobs j LEFT JOIN job_categories jc
               ON jc.job_id = j.job_id AND jc.is_primary
               WHERE jc.category_id IS DISTINCT FROM j.primary_category_id LIMIT 1""")
    assert not bad
    # tổng số dòng gốc đã gộp = số dòng CSV
    assert q("SELECT sum(source_rows) FROM jobs")[0][0] == 48092
