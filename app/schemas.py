"""Pydantic schemas cho API HAEIM_Damped."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator


class TxItem(BaseModel):
    item: str = Field(min_length=1)
    qty: float = Field(gt=0)

    @field_validator("item")
    @classmethod
    def _strip_item(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("item rỗng")
        return v


class NewTransaction(BaseModel):
    # StrictInt: tid PHẢI là số nguyên > 0 — từ chối 2.5, "8", 0, âm (strict).
    tid: Optional[StrictInt] = Field(default=None, gt=0)
    items: list[TxItem] = Field(min_length=1)


class NewItem(BaseModel):
    item: str = Field(min_length=1)
    eu: float = Field(gt=0, description="Ngoại tiện ích (external utility)")
    inv: float = Field(gt=0, description="Chi phí đầu tư tĩnh INV(i), Bảng 2")
    cu: Optional[float] = Field(default=None, gt=0)

    @field_validator("item")
    @classmethod
    def _strip_item(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("item rỗng")
        return v


class BulkTransactions(BaseModel):
    transactions: list[NewTransaction] = Field(min_length=1)


class MineRequest(BaseModel):
    f: float = Field(default=0.8, gt=0, lt=1, strict=True, description="Hệ số suy giảm, 0<f<1")
    minae: float = Field(default=0.2, ge=0, description="Ngưỡng hiệu suất trung bình tối thiểu")
    sound: StrictBool = Field(
        default=True,
        description="True = cắt tỉa bằng cận trên ÂM (không bỏ sót HAEI); "
                    "False = cận trên 1-phần-mở-rộng (nhanh hơn nhưng bỏ sót)",
    )


# ---------------------------------------------------------------- thực nghiệm
class ValidateRequest(BaseModel):
    """Kiểm chứng thuật toán cắt tỉa so với ground truth (duyệt tất cả tập mục)."""

    f: float = Field(default=0.8, gt=0, lt=1, strict=True)
    minae: float = Field(default=0.2, ge=0)
    max_tx_items: int = Field(default=16, ge=1, le=22,
                              description="Chặn an toàn: số mục tối đa/1 giao dịch")


class BenchRequest(BaseModel):
    """Đo hiệu năng: thuật toán cắt tỉa vs duyệt tất cả tập mục."""

    n_transactions: int = Field(default=200, ge=1, le=20000)
    n_items: int = Field(default=12, ge=1, le=100)
    seed: int = Field(default=42, ge=0)
    f: float = Field(default=0.8, gt=0, lt=1, strict=True)
    minae: float = Field(default=0.2, ge=0)
    with_exact: bool = Field(default=True, description="Chạy thêm ground truth để so sánh")
    max_items_per_tx: int = Field(default=6, ge=1, le=20,
                                  description="Độ dài giỏ hàng tối đa (ảnh hưởng mũ cấp của ground truth)")


class PruningComparisonRequest(BaseModel):
    """So sánh 2 chiến lược cắt tỉa: âm (an toàn) vs chặt (nhanh, bỏ sót)."""

    n_transactions: int = Field(default=1000, ge=1, le=20000)
    n_items: int = Field(default=18, ge=1, le=100)
    max_items_per_tx: int = Field(default=12, ge=1, le=20)
    seed: int = Field(default=42, ge=0)
    f: float = Field(default=0.8, gt=0, lt=1, strict=True)
    minae: float = Field(default=0.2, ge=0)


class ScalabilityRequest(BaseModel):
    """Quét nhiều kích thước luồng -> số liệu vẽ đồ thị."""

    sizes: Optional[list[dict]] = Field(
        default=None,
        description='Danh sách {"transactions": n, "items": m}; bỏ trống = bộ cố định',
    )
    f: float = Field(default=0.8, gt=0, lt=1, strict=True)
    minae: float = Field(default=0.2, ge=0)
    seed: int = Field(default=42, ge=0)
    with_exact: bool = Field(default=True)


class SweepRequest(BaseModel):
    """Quét tham số f / minae trên luồng hiện tại."""

    f_values: Optional[list[float]] = Field(default=None)
    minae_values: Optional[list[float]] = Field(default=None)


class ConstructionCostRequest(BaseModel):
    """Đo chi phí Pha 1 (Construction) — kiểm chứng O(|T_j|)."""

    n_transactions: int = Field(default=200, ge=2, le=20000)
    n_items: int = Field(default=12, ge=1, le=100)
    seed: int = Field(default=42, ge=0)


class GenerateDatasetRequest(BaseModel):
    """Sinh luồng giao dịch tổng hợp (mô phỏng dữ liệu siêu thị)."""

    n_transactions: int = Field(default=200, ge=1, le=20000)
    n_items: int = Field(default=12, ge=1, le=100)
    seed: int = Field(default=42, ge=0)
    qty_max: int = Field(default=5, ge=1, le=100)
    zipf_s: float = Field(default=1.1, gt=0)
    drift: float = Field(default=0.35, ge=0)
    min_items_per_tx: int = Field(default=2, ge=1)
    max_items_per_tx: int = Field(default=6, ge=1)
    load: bool = Field(default=True, description="Nạp luồng vào miner hay chỉ trả về")


class LoadDatasetRequest(BaseModel):
    """Nạp một bộ dữ liệu dựng sẵn theo khoá."""

    key: str = Field(min_length=1)


class ImportCsvRequest(BaseModel):
    """Nhập luồng giao dịch từ CSV (tid,item,qty).

    Nếu không cung cấp `eu`/`inv` thì suy ra tự động theo quy ước:
      eu(i) = 1.0, cu(i) = 1.0, Inv(i) = cu(i) * tổng_qty(i) trên toàn luồng
    (cùng cách suy luận Bảng 2 của PDF).
    """

    csv: str = Field(min_length=1, description="Nội dung CSV: tid,item,qty")
    eu: Optional[dict[str, float]] = None
    inv: Optional[dict[str, float]] = None
    cu: Optional[dict[str, float]] = None
    load: bool = Field(default=True)


class ExplainRequest(BaseModel):
    """Giải thích một pattern (dùng GET hoặc POST)."""

    pattern: list[str] = Field(min_length=1)
    f: float = Field(default=0.8, gt=0, lt=1, strict=True)
    minae: float = Field(default=0.2, ge=0)
