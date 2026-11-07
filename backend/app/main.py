"""VietJobs Analytics API – FastAPI.

Chạy:  cd backend && uvicorn app.main:app --reload --port 8000
Tài liệu API tự sinh: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import socket
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from pipeline.inference import models_status

from .config import CORS_ORIGINS, DASHBOARD_URL, ROOT_DIR
from .db import Job, SessionLocal, ensure_ops_schema, schema_ready
from .routers import dashboard, insights, jobs, pipeline, predict, stats

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Lược đồ do ETL tạo (database/schema.sql); ở đây chỉ kiểm tra kết nối PostgreSQL
    try:
        ensure_ops_schema()
        if not schema_ready():
            print("[!] CSDL chưa có bảng. Hãy chạy: python -m pipeline.etl")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Không kết nối được PostgreSQL ({exc}). Kiểm tra DATABASE_URL / docker compose up -d postgres")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="VietJobs Analytics API",
    description="Phân tích thị trường tuyển dụng Việt Nam, dự đoán lương & kỹ năng (đồ án Big Data).",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for r in (dashboard.router, stats.router, jobs.router, predict.router, insights.router, pipeline.router):
    app.include_router(r)


@app.exception_handler(OperationalError)
async def db_unavailable(_: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={
        "detail": "Không kết nối được PostgreSQL. Khởi động CSDL: python scripts/local_db.py start"})


@app.exception_handler(ProgrammingError)
async def schema_missing(_: Request, exc: ProgrammingError):
    return JSONResponse(status_code=503, content={
        "detail": "CSDL chưa đủ bảng. Hãy chạy pipeline: cd backend && python -m pipeline.run_all"})


def _port_open(url: str) -> bool:
    u = urlparse(url)
    try:
        with socket.create_connection((u.hostname or "localhost", u.port or 80), timeout=0.2):
            return True
    except OSError:
        return False


@app.get("/api/health", tags=["Hệ thống"])
def health():
    base = {"models": models_status(), "dashboard_url": DASHBOARD_URL, "dashboard_online": _port_open(DASHBOARD_URL)}
    with SessionLocal() as db:
        n = db.scalar(select(func.count(Job.id)))
        version = db.scalar(select(func.version()))
    return {"status": "ok", "database": version.split(" (")[0].split(" on ")[0], "jobs": n, **base}


# Nếu đã build frontend (frontend/dist) thì phục vụ luôn tại http://localhost:8000
_DIST = ROOT_DIR / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Không có API này")
        target = (_DIST / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(_DIST.resolve()):
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
