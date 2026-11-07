-- Chạy tự động khi container PostgreSQL khởi tạo lần đầu (docker-entrypoint-initdb.d)
-- CSDL riêng để Superset lưu metadata (dashboard, chart, người dùng)
CREATE DATABASE superset OWNER vietjobs;
