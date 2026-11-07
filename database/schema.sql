-- =============================================================================
--  VietJobs – Lược đồ CSDL PostgreSQL (16+)
--  Chạy:  psql -U vietjobs -d vietjobs -f database/schema.sql
--  (backend tự chạy file này khi khởi tạo: python -m pipeline.etl)
--
--  Nhóm 1 – Dữ liệu tuyển dụng (chuẩn hoá 3NF)
--      provinces, categories, skills, languages      : bảng danh mục
--      jobs                                          : bảng sự kiện (1 dòng = 1 tin tuyển dụng duy nhất)
--      job_categories, job_skills, job_languages     : bảng nối nhiều–nhiều
--  Nhóm 2 – Máy học
--      ml_training_runs -> ml_models -> model_metrics, predictions
--  Nhóm 3 – Khai phá dữ liệu
--      mining_runs -> association_rules -> rule_antecedents
--      mining_runs -> clusters -> job_clusters ; mining_runs -> cluster_k_scores ; mining_runs -> skill_salary_stats
--  Nhóm 4 – View cho dashboard BI (Superset): v_job_facts, v_job_categories, v_job_skills, v_model_results
-- =============================================================================

SET client_min_messages = warning;

DROP VIEW IF EXISTS v_model_results, v_job_skills, v_job_categories, v_job_facts CASCADE;
DROP TABLE IF EXISTS skill_salary_stats, cluster_k_scores, job_clusters, clusters, rule_antecedents,
    association_rules, mining_runs, predictions, model_metrics, ml_models, ml_training_runs,
    job_languages, job_skills, job_categories, jobs, languages, skills, categories, provinces CASCADE;

-- ---------------------------------------------------------------------------
-- 1. DANH MỤC
-- ---------------------------------------------------------------------------
CREATE TABLE provinces (
    province_id   SERIAL       PRIMARY KEY,
    name          VARCHAR(100) NOT NULL UNIQUE,              -- 'Hà Nội', 'Hồ Chí Minh', 'Nước ngoài', 'Khác'
    region        VARCHAR(20)  NOT NULL                       -- 'Miền Bắc' | 'Miền Trung' | 'Miền Nam' | 'Khác'
        CHECK (region IN ('Miền Bắc', 'Miền Trung', 'Miền Nam', 'Khác'))
);

CREATE TABLE categories (
    category_id   SERIAL       PRIMARY KEY,
    slug          VARCHAR(120) NOT NULL UNIQUE,               -- nhãn gốc trong dữ liệu, vd 'công_nghệ_thông_tin_kỹ_thuật_số'
    name          VARCHAR(200) NOT NULL                       -- tên hiển thị
);

CREATE TABLE skills (
    skill_id      SERIAL       PRIMARY KEY,
    name          VARCHAR(120) NOT NULL,                      -- tên đã chuẩn hoá, vd 'photoshop'
    kind          VARCHAR(10)  NOT NULL CHECK (kind IN ('technical', 'soft')),
    UNIQUE (name, kind)
);

CREATE TABLE languages (
    language_id   SERIAL       PRIMARY KEY,
    name          VARCHAR(60)  NOT NULL UNIQUE                -- 'tiếng anh', 'tiếng nhật', ...
);

-- ---------------------------------------------------------------------------
-- 2. TIN TUYỂN DỤNG
-- ---------------------------------------------------------------------------
CREATE TABLE jobs (
    job_id              INTEGER      PRIMARY KEY,
    title               VARCHAR(300) NOT NULL,
    title_key           VARCHAR(300) NOT NULL,                -- chức danh không dấu, chữ thường (tìm kiếm)
    province_id         INTEGER      NOT NULL REFERENCES provinces (province_id),
    primary_category_id INTEGER      NOT NULL REFERENCES categories (category_id),
    location_raw        VARCHAR(300),
    country             VARCHAR(60),
    experience_raw      VARCHAR(60),
    experience_years    NUMERIC(4, 2) CHECK (experience_years >= 0),
    experience_bucket   VARCHAR(20)  NOT NULL,                -- 'Không yêu cầu' | 'Dưới 1 năm' | '1-2 năm' | '3-5 năm' | 'Trên 5 năm' | 'Không rõ'
    contract_type       VARCHAR(60)  NOT NULL,
    salary_text         VARCHAR(120),                         -- chuỗi gốc, vd '15.0 - 22.0 triệu'
    salary_min          NUMERIC(7, 2),                        -- triệu VNĐ / tháng; NULL = thoả thuận
    salary_max          NUMERIC(7, 2),
    salary_avg          NUMERIC(7, 2),
    is_negotiable       BOOLEAN      NOT NULL DEFAULT FALSE,
    working_hours       TEXT,
    qualifications      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    benefits            JSONB        NOT NULL DEFAULT '[]'::jsonb,
    description         TEXT,
    requirements_text   TEXT,
    source_rows         SMALLINT     NOT NULL DEFAULT 1,      -- số dòng CSV gốc đã gộp vào tin này
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max),
    CHECK (is_negotiable = (salary_avg IS NULL))
);
CREATE INDEX ix_jobs_province   ON jobs (province_id);
CREATE INDEX ix_jobs_category   ON jobs (primary_category_id);
CREATE INDEX ix_jobs_salary     ON jobs (salary_avg);
CREATE INDEX ix_jobs_experience ON jobs (experience_bucket);
CREATE INDEX ix_jobs_title_key  ON jobs (title_key varchar_pattern_ops);

-- Một tin được TopCV đăng dưới nhiều ngành -> nhiều–nhiều
CREATE TABLE job_categories (
    job_id       INTEGER NOT NULL REFERENCES jobs (job_id) ON DELETE CASCADE,
    category_id  INTEGER NOT NULL REFERENCES categories (category_id),
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (job_id, category_id)
);
CREATE INDEX ix_job_categories_category ON job_categories (category_id);

CREATE TABLE job_skills (
    job_id    INTEGER NOT NULL REFERENCES jobs (job_id) ON DELETE CASCADE,
    skill_id  INTEGER NOT NULL REFERENCES skills (skill_id),
    PRIMARY KEY (job_id, skill_id)
);
CREATE INDEX ix_job_skills_skill ON job_skills (skill_id);

CREATE TABLE job_languages (
    job_id       INTEGER NOT NULL REFERENCES jobs (job_id) ON DELETE CASCADE,
    language_id  INTEGER NOT NULL REFERENCES languages (language_id),
    PRIMARY KEY (job_id, language_id)
);

-- ---------------------------------------------------------------------------
-- 3. MÁY HỌC
-- ---------------------------------------------------------------------------
-- Một lần huấn luyện cho một bài toán (salary | skills | category)
CREATE TABLE ml_training_runs (
    run_id       SERIAL      PRIMARY KEY,
    task         VARCHAR(20) NOT NULL CHECK (task IN ('salary', 'skills', 'category')),
    n_train      INTEGER     NOT NULL,
    n_val        INTEGER     NOT NULL,
    n_test       INTEGER     NOT NULL,
    report       JSONB       NOT NULL,                        -- chi tiết: ma trận nhầm lẫn, sai số theo ngành, ...
    trained_at   TIMESTAMP   NOT NULL DEFAULT now()
);

-- Các mô hình được so sánh trong một lần huấn luyện; is_best = mô hình được triển khai
CREATE TABLE ml_models (
    model_id       SERIAL       PRIMARY KEY,
    run_id         INTEGER      NOT NULL REFERENCES ml_training_runs (run_id) ON DELETE CASCADE,
    name           VARCHAR(120) NOT NULL,
    is_best        BOOLEAN      NOT NULL DEFAULT FALSE,
    artifact_path  VARCHAR(255),                              -- file .joblib (chỉ mô hình tốt nhất)
    train_seconds  NUMERIC(8, 1),
    UNIQUE (run_id, name)
);
-- Đảm bảo mỗi lần huấn luyện có tối đa 1 mô hình tốt nhất
CREATE UNIQUE INDEX ux_ml_models_best ON ml_models (run_id) WHERE is_best;

-- Chỉ số đánh giá dạng dài (model, tập, chỉ số) -> dễ vẽ biểu đồ trong BI
CREATE TABLE model_metrics (
    model_id  INTEGER     NOT NULL REFERENCES ml_models (model_id) ON DELETE CASCADE,
    split     VARCHAR(30) NOT NULL,                           -- 'val' | 'test' | 'test_description_only' | ...
    metric    VARCHAR(40) NOT NULL,                           -- 'RMSE' | 'R2' | 'Accuracy' | 'Macro_F1' | 'Precision@5' ...
    value     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (model_id, split, metric)
);

-- Lịch sử dự đoán từ giao diện web
CREATE TABLE predictions (
    prediction_id  BIGSERIAL   PRIMARY KEY,
    model_id       INTEGER     REFERENCES ml_models (model_id) ON DELETE SET NULL,
    task           VARCHAR(20) NOT NULL CHECK (task IN ('salary', 'skills', 'category')),
    input          JSONB       NOT NULL,
    output         JSONB       NOT NULL,
    created_at     TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX ix_predictions_task_time ON predictions (task, created_at DESC);

-- ---------------------------------------------------------------------------
-- 4. KHAI PHÁ DỮ LIỆU
-- ---------------------------------------------------------------------------
-- Mỗi lần chạy một thuật toán khai phá (tham số: min_support, ngưỡng lương, khoảng k, ...)
CREATE TABLE mining_runs (
    run_id      SERIAL      PRIMARY KEY,
    kind        VARCHAR(20) NOT NULL CHECK (kind IN ('association_rules', 'clustering', 'skill_salary')),
    params      JSONB       NOT NULL,
    created_at  TIMESTAMP   NOT NULL DEFAULT now()
);

-- Luật kết hợp FP-Growth:  {kỹ năng ở vế trái}  =>  vế phải (kỹ năng | ngành | nhóm lương)
CREATE TABLE association_rules (
    rule_id                 SERIAL       PRIMARY KEY,
    run_id                  INTEGER      NOT NULL REFERENCES mining_runs (run_id) ON DELETE CASCADE,
    consequent_type         VARCHAR(10)  NOT NULL CHECK (consequent_type IN ('skill', 'category', 'salary')),
    consequent_label        VARCHAR(200) NOT NULL,            -- 'excel' | 'Ngành=…' | 'Lương=Cao'
    consequent_skill_id     INTEGER      REFERENCES skills (skill_id),
    consequent_category_id  INTEGER      REFERENCES categories (category_id),
    support                 DOUBLE PRECISION NOT NULL CHECK (support > 0 AND support <= 1),
    confidence              DOUBLE PRECISION NOT NULL CHECK (confidence > 0 AND confidence <= 1),
    lift                    DOUBLE PRECISION NOT NULL,
    CHECK ((consequent_type = 'skill')    = (consequent_skill_id IS NOT NULL)),
    CHECK ((consequent_type = 'category') = (consequent_category_id IS NOT NULL))
);
CREATE INDEX ix_rules_type_lift ON association_rules (consequent_type, lift DESC);

CREATE TABLE rule_antecedents (
    rule_id   INTEGER NOT NULL REFERENCES association_rules (rule_id) ON DELETE CASCADE,
    skill_id  INTEGER NOT NULL REFERENCES skills (skill_id),
    PRIMARY KEY (rule_id, skill_id)
);

-- Phân cụm K-Means
CREATE TABLE clusters (
    cluster_id       SERIAL       PRIMARY KEY,
    run_id           INTEGER      NOT NULL REFERENCES mining_runs (run_id) ON DELETE CASCADE,
    kmeans_label     SMALLINT     NOT NULL,                   -- nhãn cụm do K-Means gán (0..k-1)
    label            VARCHAR(200) NOT NULL,                   -- chức danh phổ biến nhất trong cụm
    size             INTEGER      NOT NULL,
    median_salary    NUMERIC(7, 2),
    top_terms        JSONB        NOT NULL,
    top_skills       JSONB        NOT NULL,
    distinct_skills  JSONB        NOT NULL,                   -- kỹ năng có lift cao nhất so với toàn bộ dữ liệu
    top_soft_skills  JSONB        NOT NULL,
    example_titles   JSONB        NOT NULL,
    top_categories   JSONB        NOT NULL,
    UNIQUE (run_id, kmeans_label)
);

CREATE TABLE job_clusters (
    job_id      INTEGER NOT NULL PRIMARY KEY REFERENCES jobs (job_id) ON DELETE CASCADE,
    cluster_id  INTEGER NOT NULL REFERENCES clusters (cluster_id) ON DELETE CASCADE,
    pca_x       REAL,                                         -- toạ độ 2D (chỉ có ở tin được lấy mẫu để vẽ)
    pca_y       REAL
);
CREATE INDEX ix_job_clusters_cluster ON job_clusters (cluster_id);

CREATE TABLE cluster_k_scores (
    run_id      INTEGER  NOT NULL REFERENCES mining_runs (run_id) ON DELETE CASCADE,
    k           SMALLINT NOT NULL,
    silhouette  DOUBLE PRECISION NOT NULL,
    is_chosen   BOOLEAN  NOT NULL DEFAULT FALSE,
    PRIMARY KEY (run_id, k)
);

-- Kỹ năng & lương: lương trung vị của tin có yêu cầu kỹ năng so với toàn thị trường
CREATE TABLE skill_salary_stats (
    run_id           INTEGER NOT NULL REFERENCES mining_runs (run_id) ON DELETE CASCADE,
    skill_id         INTEGER NOT NULL REFERENCES skills (skill_id) ON DELETE CASCADE,
    n_jobs           INTEGER NOT NULL,
    n_with_salary    INTEGER NOT NULL,
    median_salary    NUMERIC(7, 2) NOT NULL,
    mean_salary      NUMERIC(7, 2) NOT NULL,
    premium_pct      NUMERIC(7, 2) NOT NULL,                  -- (trung vị kỹ năng / trung vị thị trường - 1) * 100
    top_category_id  INTEGER REFERENCES categories (category_id),
    PRIMARY KEY (run_id, skill_id)
);

-- ---------------------------------------------------------------------------
-- 5. VIEW CHO DASHBOARD BI
-- ---------------------------------------------------------------------------
-- 1 dòng / tin, đã nối danh mục; salary_valid = lương nằm trong khoảng 1–150 triệu
CREATE VIEW v_job_facts AS
SELECT j.job_id, j.title, p.name AS province, p.region, c.name AS primary_category,
       j.experience_bucket, j.experience_years, j.contract_type, j.is_negotiable,
       CASE WHEN j.salary_avg BETWEEN 1 AND 150 THEN j.salary_avg END AS salary_valid,
       j.salary_min, j.salary_max,
       EXISTS (SELECT 1 FROM job_languages l WHERE l.job_id = j.job_id) AS requires_language,
       (SELECT count(*) FROM job_skills s JOIN skills k USING (skill_id)
         WHERE s.job_id = j.job_id AND k.kind = 'technical')         AS n_technical_skills,
       (SELECT count(*) FROM job_categories jc WHERE jc.job_id = j.job_id) AS n_categories,
       cl.label AS cluster,
       CASE j.experience_bucket WHEN 'Không yêu cầu' THEN '1. Không yêu cầu' WHEN 'Dưới 1 năm' THEN '2. Dưới 1 năm'
            WHEN '1-2 năm' THEN '3. 1-2 năm' WHEN '3-5 năm' THEN '4. 3-5 năm' WHEN 'Trên 5 năm' THEN '5. Trên 5 năm'
            ELSE '6. Không rõ' END AS experience_level            -- nhãn có thứ tự để sắp xếp trên biểu đồ
FROM jobs j
JOIN provinces p  ON p.province_id = j.province_id
JOIN categories c ON c.category_id = j.primary_category_id
LEFT JOIN job_clusters jc2 ON jc2.job_id = j.job_id
LEFT JOIN clusters cl      ON cl.cluster_id = jc2.cluster_id;

-- 1 dòng / (tin, ngành): một tin đa ngành được tính ở mỗi ngành
CREATE VIEW v_job_categories AS
SELECT jc.job_id, c.name AS category, jc.is_primary, f.province, f.region, f.experience_bucket,
       f.contract_type, f.is_negotiable, f.salary_valid, f.experience_level
FROM job_categories jc
JOIN categories c  ON c.category_id = jc.category_id
JOIN v_job_facts f ON f.job_id = jc.job_id;

-- 1 dòng / (tin, kỹ năng)
CREATE VIEW v_job_skills AS
SELECT js.job_id, k.name AS skill, k.kind, f.primary_category, f.province, f.experience_bucket, f.salary_valid
FROM job_skills js
JOIN skills k      ON k.skill_id = js.skill_id
JOIN v_job_facts f ON f.job_id = js.job_id;

-- Kết quả mô hình mới nhất của mỗi bài toán
CREATE VIEW v_model_results AS
SELECT r.task, m.name AS model, m.is_best, mm.split, mm.metric, mm.value, r.trained_at
FROM model_metrics mm
JOIN ml_models m        ON m.model_id = mm.model_id
JOIN ml_training_runs r ON r.run_id = m.run_id
WHERE r.run_id IN (SELECT max(run_id) FROM ml_training_runs GROUP BY task);
