"""Ánh xạ ORM (SQLAlchemy) cho lược đồ PostgreSQL trong database/schema.sql.

schema.sql là nguồn chuẩn (khoá chính, khoá ngoại, ràng buộc CHECK, index, view);
các lớp dưới đây chỉ ánh xạ để backend truy vấn – không dùng create_all.
"""
from __future__ import annotations

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, SmallInteger,
                        String, Text, create_engine, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import DATABASE_URL, ROOT_DIR

SCHEMA_SQL = ROOT_DIR / "database" / "schema.sql"
OPS_SQL = ROOT_DIR / "database" / "pipeline_runs.sql"

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Money = Numeric(7, 2, asdecimal=False)  # triệu VNĐ, trả về float


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- danh mục
class Province(Base):
    __tablename__ = "provinces"
    id = Column("province_id", Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    region = Column(String(20), nullable=False)


class Category(Base):
    __tablename__ = "categories"
    id = Column("category_id", Integer, primary_key=True)
    slug = Column(String(120), nullable=False, unique=True)
    name = Column(String(200), nullable=False)


class Skill(Base):
    __tablename__ = "skills"
    id = Column("skill_id", Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(10), nullable=False)


class Language(Base):
    __tablename__ = "languages"
    id = Column("language_id", Integer, primary_key=True)
    name = Column(String(60), nullable=False, unique=True)


# ---------------------------------------------------------------- tin tuyển dụng
class Job(Base):
    __tablename__ = "jobs"
    id = Column("job_id", Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    title_key = Column(String(300), nullable=False)
    province_id = Column(Integer, ForeignKey("provinces.province_id"), nullable=False)
    category_id = Column("primary_category_id", Integer, ForeignKey("categories.category_id"), nullable=False)
    location_raw = Column(String(300))
    country = Column(String(60))
    experience_raw = Column(String(60))
    experience_years = Column(Numeric(4, 2, asdecimal=False))
    experience_bucket = Column(String(20), nullable=False)
    contract_type = Column(String(60), nullable=False)
    salary_raw = Column("salary_text", String(120))
    salary_min = Column(Money)
    salary_max = Column(Money)
    salary_avg = Column(Money)
    is_negotiable = Column(Boolean, nullable=False, default=False)
    working_hours = Column(Text)
    qualifications = Column(JSONB, nullable=False, default=list)
    benefits = Column(JSONB, nullable=False, default=list)
    description = Column(Text)
    requirements_text = Column(Text)
    source_rows = Column(SmallInteger, nullable=False, default=1)

    category = relationship("Category")
    categories = relationship("Category", secondary="job_categories", viewonly=True)
    province = relationship("Province")
    skills = relationship("Skill", secondary="job_skills", viewonly=True)
    languages = relationship("Language", secondary="job_languages", viewonly=True)


class JobCategory(Base):
    __tablename__ = "job_categories"
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.category_id"), primary_key=True)
    is_primary = Column(Boolean, nullable=False, default=False)


class JobSkill(Base):
    __tablename__ = "job_skills"
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.skill_id"), primary_key=True)


class JobLanguage(Base):
    __tablename__ = "job_languages"
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    language_id = Column(Integer, ForeignKey("languages.language_id"), primary_key=True)


# ---------------------------------------------------------------- máy học
class TrainingRun(Base):
    __tablename__ = "ml_training_runs"
    id = Column("run_id", Integer, primary_key=True)
    task = Column(String(20), nullable=False)
    n_train = Column(Integer, nullable=False)
    n_val = Column(Integer, nullable=False)
    n_test = Column(Integer, nullable=False)
    report = Column(JSONB, nullable=False)
    trained_at = Column(DateTime, nullable=False, server_default=func.now())
    models = relationship("MLModel", back_populates="run")


class MLModel(Base):
    __tablename__ = "ml_models"
    id = Column("model_id", Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("ml_training_runs.run_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    is_best = Column(Boolean, nullable=False, default=False)
    artifact_path = Column(String(255))
    train_seconds = Column(Numeric(8, 1, asdecimal=False))
    run = relationship("TrainingRun", back_populates="models")
    metrics = relationship("ModelMetric")


class ModelMetric(Base):
    __tablename__ = "model_metrics"
    model_id = Column(Integer, ForeignKey("ml_models.model_id", ondelete="CASCADE"), primary_key=True)
    split = Column(String(30), primary_key=True)
    metric = Column(String(40), primary_key=True)
    value = Column(Float, nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column("prediction_id", BigInteger, primary_key=True)
    model_id = Column(Integer, ForeignKey("ml_models.model_id", ondelete="SET NULL"))
    task = Column(String(20), nullable=False)
    input = Column(JSONB, nullable=False)
    output = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------- khai phá dữ liệu
class MiningRun(Base):
    __tablename__ = "mining_runs"
    id = Column("run_id", Integer, primary_key=True)
    kind = Column(String(20), nullable=False)
    params = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AssociationRule(Base):
    __tablename__ = "association_rules"
    id = Column("rule_id", Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("mining_runs.run_id", ondelete="CASCADE"), nullable=False)
    consequent_type = Column(String(10), nullable=False)
    consequent_label = Column(String(200), nullable=False)
    consequent_skill_id = Column(Integer, ForeignKey("skills.skill_id"))
    consequent_category_id = Column(Integer, ForeignKey("categories.category_id"))
    support = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    lift = Column(Float, nullable=False)
    antecedents = relationship("Skill", secondary="rule_antecedents", viewonly=True)


class RuleAntecedent(Base):
    __tablename__ = "rule_antecedents"
    rule_id = Column(Integer, ForeignKey("association_rules.rule_id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.skill_id"), primary_key=True)


class Cluster(Base):
    __tablename__ = "clusters"
    id = Column("cluster_id", Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("mining_runs.run_id", ondelete="CASCADE"), nullable=False)
    kmeans_label = Column(SmallInteger, nullable=False)
    label = Column(String(200), nullable=False)
    size = Column(Integer, nullable=False)
    median_salary = Column(Money)
    top_terms = Column(JSONB, nullable=False)
    top_skills = Column(JSONB, nullable=False)
    distinct_skills = Column(JSONB, nullable=False)
    top_soft_skills = Column(JSONB, nullable=False)
    example_titles = Column(JSONB, nullable=False)
    top_categories = Column(JSONB, nullable=False)


class JobCluster(Base):
    __tablename__ = "job_clusters"
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    cluster_id = Column(Integer, ForeignKey("clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    pca_x = Column(Float)
    pca_y = Column(Float)


class ClusterKScore(Base):
    __tablename__ = "cluster_k_scores"
    run_id = Column(Integer, ForeignKey("mining_runs.run_id", ondelete="CASCADE"), primary_key=True)
    k = Column(SmallInteger, primary_key=True)
    silhouette = Column(Float, nullable=False)
    is_chosen = Column(Boolean, nullable=False, default=False)


class SkillSalaryStat(Base):
    __tablename__ = "skill_salary_stats"
    run_id = Column(Integer, ForeignKey("mining_runs.run_id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.skill_id", ondelete="CASCADE"), primary_key=True)
    n_jobs = Column(Integer, nullable=False)
    n_with_salary = Column(Integer, nullable=False)
    median_salary = Column(Money, nullable=False)
    mean_salary = Column(Money, nullable=False)
    premium_pct = Column(Money, nullable=False)
    top_category_id = Column(Integer, ForeignKey("categories.category_id"))
    skill = relationship("Skill")
    top_category = relationship("Category")


# ---------------------------------------------------------------- vận hành pipeline
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id = Column("run_id", Integer, primary_key=True)
    job = Column(String(30), nullable=False)
    status = Column(String(10), nullable=False, default="running")
    trigger = Column(String(10), nullable=False, default="cli")
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime)
    seconds = Column(Numeric(10, 1, asdecimal=False))
    rows_in = Column(Integer)
    rows_out = Column(Integer)
    detail = Column(JSONB, nullable=False, default=dict)
    log_tail = Column(Text)


# ---------------------------------------------------------------- tiện ích
def _run_sql_file(path) -> None:
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


def ensure_ops_schema() -> None:
    """Tạo bảng nhật ký pipeline nếu chưa có (an toàn khi gọi nhiều lần)."""
    _run_sql_file(OPS_SQL)


def create_schema() -> None:
    """Tạo lại toàn bộ lược đồ từ database/schema.sql (XOÁ dữ liệu cũ, giữ nhật ký pipeline_runs)."""
    _run_sql_file(SCHEMA_SQL)
    ensure_ops_schema()


def schema_ready() -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('public.jobs') IS NOT NULL")).scalar())


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
