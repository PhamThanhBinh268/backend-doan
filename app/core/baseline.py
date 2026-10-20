"""Brute-force ground truth cho HAEIM_Damped — nền tảng kiểm chứng độ đúng.

Vì sao cần module này?
----------------------
Thuật toán HAEIM_Damped **cắt tỉa** (pruning) rất mạnh ở Pha 2 (lọc SMDAEUB,
STDAEUB) và Pha 3 (LTDAEUB) để chạy nhanh trên luồng dài. Nhưng cắt tỉa chỉ
được chấp nhận trong luận văn khi chứng minh được: **không bỏ sót HAEI nào**.

`exact_mine` ở đây là cách kiểm chứng độc lập, hoàn toàn không dùng cắt tỉa:
duyệt **mọi** tập mục con của mọi giao dịch, tính đúng `Sdae` theo định nghĩa
(Công thức 5) rồi lọc `Sdae >= minae`. Kết quả là "đáp án đúng" (ground truth)
để đối chiếu với thuật toán có cắt tỉa.

Định nghĩa dùng chung với `haeim_damped.py` (phải khớp tuyệt đối):
  u(X,Tj)  = sum_{i in X} qty(i,Tj) * eu(i)
  Inv(X)   = sum_{i in X} INV[i]
  ae(X,Tj) = u(X,Tj) / (Inv(X) * |X|)          <- Công thức 5 (hiệu suất TB)
  dae      = ae * f^(Ltid - tid)
  Sdae(X)  = sum_{Tj chứa X} dae
  HAEI     <=> Sdae(X) >= minae

Độ phức tạp: O(sum_j 2^|T_j|) — vì chỉ những tập mục **có mặt trong một giao
dịch** mới có Sdae khác 0, nên duyệt tập mục con của từng giao dịch là đủ và
*đầy đủ* (không bỏ sót tập mục nào). Đây chính là lý do ground truth khả
dụng làm chuẩn: nó "chậm nhưng chắc".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

__all__ = [
    "ExactResult",
    "exact_mine",
    "compare_with_exact",
    "canonical",
    "MAX_TX_ITEMS",
]

# Số mục tối đa trong 1 giao dịch mà ground truth chịu duyệt (2^20 = 1M tập mục
# con -> quá nặng cho Python). Vượt ngưỡng -> raise, KHÔNG âm thầm cắt bớt (sai
# lệch ngữ nghĩa) — benchmark sẽ tự chọn kích thước phù hợp.
MAX_TX_ITEMS = 16


def canonical(pattern) -> tuple[str, ...]:
    """Chuẩn tắc hoá pattern thành tuple item đã sắp xếp (để so sánh tập hợp)."""
    return tuple(sorted(pattern))


@dataclass(slots=True)
class ExactResult:
    """Kết quả ground truth + chỉ số đo để báo cáo thực nghiệm."""

    dhaeis: list[dict] = field(default_factory=list)
    #: tổng số tập mục đã duyệt (đơn vị "itemsets examined")
    itemsets_examined: int = 0
    elapsed_ms: float = 0.0
    #: số giao dịch đã duyệt
    transactions: int = 0
    #: số mục khác nhau trong luồng
    items: int = 0
    #: Ltid dùng để tính suy giảm
    ltid: int = 0

    @property
    def patterns(self) -> set[tuple[str, ...]]:
        return {canonical(d["pattern"]) for d in self.dhaeis}


def exact_mine(
    transactions: dict[int, dict[str, float]],
    eu: dict[str, float],
    inv_table: dict[str, float],
    f: float,
    minae: float,
    max_tx_items: int = MAX_TX_ITEMS,
) -> ExactResult:
    """Duyệt tất cả tập mục — không cắt tỉa — để lấy đáp án đúng.

    Tham số
    -------
    transactions : {tid: {item: qty}}
    eu, inv_table: bảng ngoại tiện ích / chi phí đầu tư tĩnh
    f             : hệ số suy giảm (0<f<1)
    minae         : ngưỡng hiệu suất trung bình tối thiểu
    max_tx_items  : chặn an toàn (không cắt ngữ nghĩa — raise nếu vượt)
    """
    f = float(f)
    minae = float(minae)
    if not 0.0 < f < 1.0:
        raise ValueError("f phải thỏa 0<f<1")
    if minae < 0:
        raise ValueError("minae phải >= 0")
    if not transactions:
        raise ValueError("Luồng rỗng")

    ltid = max(transactions)
    t0 = time.perf_counter()

    sdae: dict[tuple[str, ...], float] = {}
    examined = 0

    for tid in sorted(transactions):
        tmap = transactions[tid]
        items = sorted(tmap)
        n = len(items)
        if n > max_tx_items:
            raise ValueError(
                f"Giao dịch tid={tid} có {n} mục (> max_tx_items={max_tx_items}); "
                "ground truth không thể duyệt — hãy dùng kích thước nhỏ hơn."
            )
        utils = [tmap[i] * eu.get(i, 0.0) for i in items]
        invs = [inv_table.get(i, 0.0) for i in items]

        total = 1 << n
        # mảng phụ trợ theo mask: u(mask), Inv(mask), popcount(mask)
        su = [0.0] * total
        si = [0.0] * total
        pc = [0] * total
        # trọng số suy giảm của giao dịch này
        w = f ** (ltid - tid)
        for mask in range(1, total):
            low = mask & -mask
            j = low.bit_length() - 1
            rest = mask ^ low
            su[mask] = su[rest] + utils[j]
            si[mask] = si[rest] + invs[j]
            pc[mask] = pc[rest] + 1
            inv = si[mask]
            if inv <= 0:
                continue
            ae = su[mask] / (inv * pc[mask])          # Công thức 5
            key = tuple(items[k] for k in range(n) if (mask >> k) & 1)
            sdae[key] = sdae.get(key, 0.0) + ae * w
            examined += 1

    dhaeis = [
        {"pattern": list(k), "sdae": round(v, 6)}
        for k, v in sdae.items()
        if v >= minae
    ]
    dhaeis.sort(key=lambda d: (len(d["pattern"]), d["pattern"]))
    elapsed = (time.perf_counter() - t0) * 1000
    return ExactResult(
        dhaeis=dhaeis,
        itemsets_examined=examined,
        elapsed_ms=round(elapsed, 3),
        transactions=len(transactions),
        items=len({i for t in transactions.values() for i in t}),
        ltid=ltid,
    )


def compare_with_exact(
    pruned_patterns,
    exact: ExactResult,
) -> dict:
    """Đối chiếu tập HAEI của thuật toán cắt tỉa với ground truth.

    Trả về báo cáo dùng cho cả API lẫn test:
      matched / missing / extra — phân tích chênh lệch
      agreement — tỉ lệ khớp (1.0 = cắt tỉa không bỏ sót, không sinh thừa)
    """
    pruned = {canonical(p) for p in pruned_patterns}
    truth = exact.patterns
    matched = pruned & truth
    missing = truth - pruned      # ground truth có, thuật toán bỏ sót (không an toàn)
    extra = pruned - truth        # thuật toán sinh thừa (cắt tỉa quá tay)
    union = pruned | truth
    return {
        "exact_count": len(truth),
        "pruned_count": len(pruned),
        "matched_count": len(matched),
        "missing": [list(p) for p in sorted(missing)],
        "extra": [list(p) for p in sorted(extra)],
        "agreement": round(len(matched) / len(union), 6) if union else 1.0,
        "sound": not missing,          # không bỏ sót HAEI
        "complete": not extra,         # không sinh thừa
        "itemsets_examined": exact.itemsets_examined,
        "exact_elapsed_ms": exact.elapsed_ms,
    }
