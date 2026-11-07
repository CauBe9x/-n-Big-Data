-- Nhật ký chạy pipeline: mỗi bước (ETL, huấn luyện, khai phá, kiểm định, Spark) ghi 1 dòng.
-- Tách khỏi schema.sql vì bảng này KHÔNG bị xoá khi chạy lại ETL: lịch sử chạy phải sống qua các lần nạp lại dữ liệu.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       SERIAL      PRIMARY KEY,
    job          VARCHAR(30) NOT NULL,                     -- 'etl' | 'salary' | 'skills' | 'category' | 'mining' | 'quality' | 'reconcile' | 'spark'
    status       VARCHAR(10) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    trigger      VARCHAR(10) NOT NULL DEFAULT 'cli' CHECK (trigger IN ('cli', 'ui')),
    started_at   TIMESTAMP   NOT NULL DEFAULT now(),
    finished_at  TIMESTAMP,
    seconds      NUMERIC(10, 1),
    rows_in      INTEGER,
    rows_out     INTEGER,
    detail       JSONB       NOT NULL DEFAULT '{}'::jsonb, -- báo cáo chi tiết của bước (vd. hồ sơ chất lượng dữ liệu)
    log_tail     TEXT
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_job_time ON pipeline_runs (job, run_id DESC);
