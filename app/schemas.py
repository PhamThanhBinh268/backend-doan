"""Pydantic schemas cho API HAEIM_Damped."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class TxItem(BaseModel):
    item: str
    qty: float = Field(gt=0)


class NewTransaction(BaseModel):
    tid: Optional[int] = None
    items: List[TxItem]


class MineRequest(BaseModel):
    f: float = Field(default=0.8, gt=0, lt=1, description="Hệ số suy giảm, 0<f<1")
    minae: float = Field(default=0.2, ge=0, description="Ngưỡng hiệu suất trung bình tối thiểu")
