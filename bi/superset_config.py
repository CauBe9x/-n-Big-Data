"""Cấu hình Apache Superset cho dashboard VietJobs.

Dùng bằng biến môi trường:  SUPERSET_CONFIG_PATH=bi/superset_config.py
"""
import os

# Khoá bí mật cho phiên đăng nhập – đổi khi triển khai thật
SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY", "vietjobs-local-dev-secret-key-change-me-please")

# CSDL metadata của Superset (lưu dashboard, chart, người dùng) – tách khỏi CSDL nghiệp vụ 'vietjobs'
SQLALCHEMY_DATABASE_URI = os.getenv(
    "SUPERSET_METADATA_URI", "postgresql+psycopg2://vietjobs:vietjobs@localhost:5432/superset")

# Giao diện tiếng Việt chưa đầy đủ trong Superset -> giữ tiếng Anh cho menu, nội dung chart vẫn tiếng Việt
BABEL_DEFAULT_LOCALE = "en"

# Cho phép nhúng & xem dashboard công khai trên máy local (đồ án)
WTF_CSRF_ENABLED = False
TALISMAN_ENABLED = False
FEATURE_FLAGS = {"DASHBOARD_NATIVE_FILTERS": True, "DASHBOARD_CROSS_FILTERS": True}
ROW_LIMIT = 50000
