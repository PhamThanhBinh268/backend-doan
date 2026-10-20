"""Sinh & quản lý bộ dữ liệu luồng giao dịch cho thực nghiệm HAEIM_Damped.

PDF chỉ cho 8 giao dịch mẫu (Bảng 1) — đủ để kiểm chứng công thức nhưng
**không đủ để đo hiệu năng**. Module này bổ sung:

1. `generate_stream` — bộ sinh luồng giao dịch tổng hợp theo mô hình
   "siêu thị" (giống dữ liệu basket analysis):
     * phổ biến item theo Zipf (vài mục bán chạy, nhiều mục hiếm),
     * **drift theo thời gian** (mục lên/xuống thị phần) — đây là lý do hệ số
       suy giảm `f^(Ltid-tid)` có ý nghĩa,
     * số lượng mua ngẫu nhiên 1..qty_max.
   Toàn bộ **tất định theo seed** (random.Random(seed)) để kết quả thực nghiệm
   tái lập được khi bảo vệ luận văn.

2. `stream_to_csv` / `parse_csv` — xuất/nhập CSV để nạp dữ liệu thật
   (định dạng: `tid;item;qty` hoặc `tid,item,qty`).

3. Bảng dữ liệu mặc định (`list_datasets`): luồng Bảng 1 của PDF + các bộ
   sinh sẵn ở quy mô khác nhau để vẽ đồ thị scalability.

Mô hình chi phí bám sát Bảng 2 của PDF: `Inv(i) = cu(i) * tổng_qty(i)` — cùng
cách suy luận mà README mô tả ("inv(i) = cu(i) * tổng_qty(i) trên toàn luồng").
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .data import CU, EU, EXAMPLE_STREAM, INV

__all__ = [
    "StreamDataset",
    "DatasetMeta",
    "generate_stream",
    "list_datasets",
    "load_dataset",
    "stream_to_csv",
    "parse_csv",
    "ITEM_NAMES",
]

# Tên mục ngắn gợi ý: a..z cho <=26 mục, sau đó i01..i99
ITEM_NAMES = [chr(ord("a") + i) for i in range(26)] + [
    f"i{n:02d}" for n in range(1, 100)
]


@dataclass(slots=True)
class StreamDataset:
    """Một bộ dữ liệu luồng giao dịch hoàn chỉnh (giao dịch + bảng chi phí)."""

    transactions: dict[int, dict[str, float]]
    eu: dict[str, float]
    inv_table: dict[str, float]
    cu: dict[str, float] = field(default_factory=dict)
    name: str = "custom"
    description: str = ""
    #: hệ số hiệu chuẩn thang đo đã áp cho INV (1.0 = không hiệu chuẩn).
    #: Quan hệ luôn đúng: Inv(i) = cu(i) * tổng_qty(i) * calibration_factor
    calibration_factor: float = 1.0

    @property
    def n_transactions(self) -> int:
        return len(self.transactions)

    @property
    def n_items(self) -> int:
        return len(self.eu)

    @property
    def ltid(self) -> int:
        return max(self.transactions) if self.transactions else 0

    def summary(self) -> dict:
        """Thông tin tóm tắt để hiển thị trên UI + API."""
        qty_total = sum(
            q for t in self.transactions.values() for q in t.values()
        )
        sizes = [len(t) for t in self.transactions.values()]
        return {
            "name": self.name,
            "description": self.description,
            "transactions": self.n_transactions,
            "items": self.n_items,
            "ltid": self.ltid,
            "total_quantity": round(qty_total, 2),
            "avg_items_per_tx": round(sum(sizes) / len(sizes), 2) if sizes else 0,
            "max_items_per_tx": max(sizes) if sizes else 0,
        }


def _item_names(n_items: int) -> list[str]:
    if n_items <= len(ITEM_NAMES):
        return ITEM_NAMES[:n_items]
    raise ValueError(f"n_items tối đa {len(ITEM_NAMES)}")


def generate_stream(
    n_transactions: int = 200,
    n_items: int = 12,
    seed: int = 42,
    qty_max: int = 5,
    zipf_s: float = 1.1,
    drift: float = 0.35,
    min_items_per_tx: int = 2,
    max_items_per_tx: int = 6,
    name: str = "generated",
    description: str = "",
    calibrate_target: float | None = 0.35,
) -> StreamDataset:
    """Sinh luồng giao dịch tổng hợp mô phỏng dữ liệu siêu thị.

    Tham số
    -------
    n_transactions   : số giao dịch
    n_items          : số mục khác nhau
    seed             : hạt giống (tất định — cùng seed cho cùng kết quả)
    qty_max          : số lượng lớn nhất mỗi mục trong 1 giao dịch
    zipf_s           : độ lệch phổ biến (số lớn -> phân bố càng tập trung)
    drift            : cường độ trôi thị phần theo thời gian (0 = không trôi)
    min/max_items_per_tx: độ dài giỏ hàng
    calibrate_target : **hiệu chuẩn thang đo** — đặt Sdae trung vị của các
                      singleton (tại f=0.8) về đúng giá trị này. Nhờ vậy dữ liệu
                      tổng hợp rơi vào vùng làm việc tương tự Bảng 1 của PDF
                      (nơi ngưỡng mặc định minae=0.2 là có ý nghĩa), thay vì
                      mọi mục đều quá nhỏ. Đặt None để tắt.
    """
    if n_transactions <= 0:
        raise ValueError("n_transactions phải > 0")
    if n_items <= 0:
        raise ValueError("n_items phải > 0")
    if not 1 <= min_items_per_tx <= max_items_per_tx:
        raise ValueError("min_items_per_tx/max_items_per_tx không hợp lệ")
    if qty_max <= 0:
        raise ValueError("qty_max phải > 0")

    rng = random.Random(seed)
    names = _item_names(n_items)

    # --- tham số ngoại tiện ích / chi phí đơn vị (Bảng 2 mở rộng) ---
    eu = {nm: round(rng.uniform(1.0, 6.0), 1) for nm in names}
    cu = {nm: round(rng.uniform(1.0, 20.0), 1) for nm in names}

    # --- phổ biến gốc theo Zipf ---
    weights = [1.0 / ((i + 1) ** zipf_s) for i in range(n_items)]
    total_w = sum(weights)
    probs = [w / total_w for w in weights]

    # --- trôi thị phần: random walk LOG có hồi phục (mean-reverting) ---
    # Nếu dùng random walk thuần, phương sai tích luỹ theo số giao dịch và
    # một vài mục sẽ "chiếm sạch" thị trường (không thực tế). Hồi phục giữ
    # phân bố ổn định: std(log w) ≈ sigma/sqrt(2·theta).
    theta = 0.02
    logw = [0.0] * n_items

    transactions: dict[int, dict[str, float]] = {}
    for tid in range(1, n_transactions + 1):
        if drift > 0:
            for i in range(n_items):
                logw[i] = (1.0 - theta) * logw[i] + drift * rng.gauss(0.0, 1.0)
            cur = [weights[i] * math.exp(logw[i]) for i in range(n_items)]
            total_w = sum(cur)
            probs = [w / total_w for w in cur]
        k = rng.randint(min_items_per_tx, min(max_items_per_tx, n_items))
        # lấy mẫu không lặp lại theo trọng số (cumulative sampling)
        chosen: list[str] = []
        pool = list(range(n_items))
        for _ in range(k):
            r = rng.random()
            acc = 0.0
            pick = pool[-1]
            for idx in pool:
                acc += probs[idx]
                if r <= acc:
                    pick = idx
                    break
            chosen.append(names[pick])
            pool.remove(pick)
        tmap: dict[str, float] = {}
        for nm in chosen:
            tmap[nm] = tmap.get(nm, 0.0) + float(rng.randint(1, qty_max))
        transactions[tid] = tmap

    # --- Inv(i) = cu(i) * tổng_qty(i) trên toàn luồng (như Bảng 2 của PDF) ---
    inv_table: dict[str, float] = {}
    for nm in names:
        qty_sum = sum(t.get(nm, 0.0) for t in transactions.values())
        inv_table[nm] = round(cu[nm] * qty_sum, 2) if qty_sum > 0 else cu[nm]

    # --- hiệu chuẩn thang đo: đưa Sdae trung vị của singleton về vùng làm việc ---
    # Co giãn INV (không phải EU) để giữ ngoại tiện ích ở mức "hợp lý" 1..6.
    calib = 1.0
    if calibrate_target and calibrate_target > 0:
        calib = _calibration_factor(transactions, eu, inv_table, calibrate_target)
        inv_table = {nm: round(v * calib, 6) for nm, v in inv_table.items()}

    desc = description or (
        f"Luồng tổng hợp {n_transactions} GD / {n_items} mục (seed={seed}, "
        f"Zipf s={zipf_s}, drift={drift})"
    )
    return StreamDataset(
        transactions=transactions,
        eu=eu,
        inv_table=inv_table,
        cu=cu,
        name=name,
        description=desc,
        calibration_factor=calib,
    )


def _calibration_factor(
    transactions: dict[int, dict[str, float]],
    eu: dict[str, float],
    inv_table: dict[str, float],
    target: float,
    f: float = 0.8,
) -> float:
    """Hệ số co giãn INV để Sdae trung vị của singleton = `target`.

    Vì `ae = u/(Inv·|X|)` nên Sdae **tỉ lệ nghịch** với Inv: nhân Inv lên c
    lúc thì Sdae chia c. Ta chọn co giãn INV (giữ EU ở mức 1..6 hợp lý) thay
    vì nhân EU lên (làm EU mất ý nghĩa và dễ phình to).

    Trung vị (không phải trung bình) để tránh vài mục "siêu sao" kéo lệch.
    Hệ số được chặn trong [1e-3, 1e3] để dữ liệu luôn ở thang đo hợp lý.
    """
    ltid = max(transactions) if transactions else 0
    sdaes: list[float] = []
    for nm, inv in inv_table.items():
        if inv <= 0:
            continue
        s = 0.0
        for tid, tmap in transactions.items():
            q = tmap.get(nm, 0.0)
            if q <= 0:
                continue
            s += (q * eu.get(nm, 0.0)) / inv * (f ** (ltid - tid))
        if s > 0:
            sdaes.append(s)
    if not sdaes:
        return 1.0
    sdaes.sort()
    mid = len(sdaes) // 2
    median = sdaes[mid] if len(sdaes) % 2 else (sdaes[mid - 1] + sdaes[mid]) / 2
    if median <= 0:
        return 1.0
    return min(1000.0, max(1e-3, median / target))


def math_exp(x: float) -> float:
    """e**x — giữ lại alias cho code cũ gọi, nay dùng math.exp trực tiếp."""
    return math.exp(x)


# --------------------------------------------------------------- bộ dữ liệu mặc định
_BUILTIN_CACHE: dict[str, StreamDataset] = {}


def _paper_dataset() -> StreamDataset:
    return StreamDataset(
        transactions={tid: dict(t) for tid, t in EXAMPLE_STREAM.items()},
        eu=dict(EU),
        inv_table=dict(INV),
        cu=dict(CU),
        name="bang1_paper",
        description="Bảng 1 của PDF (8 giao dịch mẫu) — dùng để đối chiếu công thức",
    )


def list_datasets() -> list[dict]:
    """Danh sách bộ dữ liệu dựng sẵn (metadata, chưa sinh dữ liệu)."""
    return [
        {"key": "bang1_paper", "name": "Bảng 1 (PDF)", "transactions": 8,
         "items": 6, "seed": None, "description": "Luồng mẫu gốc — khớp mọi ví dụ PDF"},
        {"key": "market_200", "name": "Market 200", "transactions": 200,
         "items": 12, "seed": 7, "description": "Luồng siêu thị 200 GD / 12 mục"},
        {"key": "market_1000", "name": "Market 1000", "transactions": 1000,
         "items": 18, "seed": 42, "description": "Luồng lớn 1000 GD / 18 mục"},
    ]


def load_dataset(key: str) -> StreamDataset:
    """Nạp bộ dữ liệu dựng sẵn theo khoá."""
    key = (key or "").strip()
    if key in _BUILTIN_CACHE:
        return _BUILTIN_CACHE[key]
    if key == "bang1_paper":
        ds = _paper_dataset()
    elif key == "market_200":
        ds = generate_stream(200, 12, seed=7, name=key,
                             description="Luồng siêu thị 200 GD / 12 mục (seed=7)")
    elif key == "market_1000":
        ds = generate_stream(1000, 18, seed=42, name=key,
                             description="Luồng lớn 1000 GD / 18 mục (seed=42)")
    else:
        raise ValueError(
            f"Không có bộ dữ liệu '{key}'. Chọn: "
            + ", ".join(d["key"] for d in list_datasets())
        )
    _BUILTIN_CACHE[key] = ds
    return ds


# ------------------------------------------------------------------- CSV I/O
def stream_to_csv(transactions: dict[int, dict[str, float]]) -> str:
    """Xuất luồng ra CSV `tid,item,qty` (mỗi dòng 1 cặp mục–số lượng)."""
    lines = ["tid,item,qty"]
    for tid in sorted(transactions):
        for item, qty in sorted(transactions[tid].items()):
            lines.append(f"{tid},{item},{qty:g}")
    return "\n".join(lines) + "\n"


def parse_csv(text: str) -> dict[int, dict[str, float]]:
    """Đọc CSV `tid,item,qty` (chấp nhận phân cáchch `,` hoặc `;`, bỏ dòng đầu
    nếu là header chữa) -> luồng giao dịch.
    """
    out: dict[int, dict[str, float]] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in (line.split(";") if ";" in line else line.split(","))]
        if len(parts) < 3:
            raise ValueError(f"Dòng {lineno}: cần 'tid,item,qty' — nhận '{raw}'")
        if lineno == 1 and not parts[0].isdigit():
            continue  # bỏ header
        try:
            tid = int(float(parts[0]))
            qty = float(parts[2])
        except ValueError as exc:
            raise ValueError(f"Dòng {lineno}: tid/qty không hợp lệ — {exc}") from exc
        item = parts[1]
        if not item:
            raise ValueError(f"Dòng {lineno}: item rỗng")
        if qty <= 0:
            raise ValueError(f"Dòng {lineno}: qty phải > 0")
        bucket = out.setdefault(tid, {})
        bucket[item] = bucket.get(item, 0.0) + qty
    if not out:
        raise ValueError("CSV không có dòng dữ liệu nào")
    return out
