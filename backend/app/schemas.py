"""Pydantic schemas cho request của API dự đoán."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SalaryInput(BaseModel):
    title: str = Field(..., min_length=2, max_length=300, examples=["Lập trình viên Java"])
    province: str | None = Field(None, examples=["Hồ Chí Minh"])
    experience_years: float | None = Field(None, ge=0, le=40, examples=[2])
    contract_type: str | None = Field("Toàn thời gian")
    category: str | None = Field(None, description="slug ngành; bỏ trống -> hệ thống tự phân loại từ chức danh")
    skills: list[str] = Field(default_factory=list, examples=[["java", "sql", "git"]])
    languages: list[str] = Field(default_factory=list, examples=[["tiếng anh"]])


class TextInput(BaseModel):
    title: str = Field(..., min_length=2, max_length=300, examples=["Kế toán tổng hợp"])
    description: str | None = Field(None, max_length=8000)
    top_k: int = Field(15, ge=1, le=50)
