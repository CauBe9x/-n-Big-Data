"""API Dashboard: toàn bộ số liệu của một trạng thái bộ lọc, trả về trong một lần gọi."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import analytics as A
from ..db import get_session

router = APIRouter(prefix="/api", tags=["Dashboard"])

Region = Literal["Miền Bắc", "Miền Trung", "Miền Nam", "Khác"]
Experience = Literal["Không yêu cầu", "Dưới 1 năm", "1-2 năm", "3-5 năm", "Trên 5 năm", "Không rõ"]


@router.get("/dashboard")
def dashboard(region: Region | None = None,
              province: str | None = Query(None, max_length=100),
              category: str | None = Query(None, max_length=120, description="slug ngành, lấy từ /api/meta"),
              experience: Experience | None = None,
              contract_type: str | None = Query(None, max_length=60),
              db: Session = Depends(get_session)):
    return A.dashboard(db, A.Filters(region, province, category, experience, contract_type))
