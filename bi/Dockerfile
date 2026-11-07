# Superset kèm driver PostgreSQL (image chính thức từ 5.x không cài sẵn driver CSDL)
FROM apache/superset:6.1.0
USER root
RUN . /app/.venv/bin/activate && uv pip install --no-cache psycopg2-binary
USER superset
