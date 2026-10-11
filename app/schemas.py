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


class NewItem(BaseModel):
    item: str = Field(min_length=1)
    eu: float = Field(gt=0, description="Ngoại tiện ích (external utility)")
    inv: float = Field(gt=0, description="Chi phí đầu tư tĩnh INV(i), Bảng 2")
    cu: Optional[float] = Field(default=None, gt=0)


class BulkTransactions(BaseModel):
    transactions: List[NewTransaction] = Field(min_length=1)


class MineRequest(BaseModel):
    f: float = Field(default=0.8, gt=0, lt=1, description="Hệ số suy giảm, 0<f<1")
    minae: float = Field(default=0.2, ge=0, description="Ngưỡng hiệu suất trung bình tối thiểu")
