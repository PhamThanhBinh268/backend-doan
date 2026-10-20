"""Đo đạc hiệu năng & thực nghiệm cho HAEIM_Damped.

Câu hỏi mà luận văn phải trả lời bằng số liệu:
  1. Thuật toán có cắt tỉa **nhanh hơn** bao nhiêu so với duyệt tất cả tập mục?
  2. Cắt tỉa có **an toàn** không (không bỏ sót HAEI)?
  3. Chi phí Pha 1 (Construction) có đúng là **O(|T_j|)** — tức không quét lại
     dữ liệu cũ — khi luồng dài ra?
  4. Kết quả thay đổi thế nào theo tham số `f` (suy giảm) và `minae` (ngưỡng)?

Module này gói các phép đo đó thành API gọi được từ HTTP, trả về số liệu
thuần để frontend vẽ biểu đồ và đưa vào phụ lục luận văn.

Nguyên tắc: **không sửa trạng thái miner đang chạy** — mọi phép đo chạy trên
bản sao (clone) của luồng nên người dùng đang xem kết quả không bị ảnh hưởng.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .baseline import ExactResult, compare_with_exact, exact_mine
from .datasets import StreamDataset, generate_stream
from .haeim_damped import HAEIMDampedMiner

__all__ = [
    "clone_miner",
    "build_miner",
    "BenchmarkRow",
    "run_benchmark",
    "run_scalability",
    "run_sweep",
    "measure_construction_cost",
    "run_pruning_comparison",
]


def clone_miner(miner: HAEIMDampedMiner) -> HAEIMDampedMiner:
    """Tạo bản sao độc lập của miner (cùng luồng + bảng chi phí).

    Dùng cho mọi phép đo/sweep để không làm bẩn trạng thái đang phục vụ.
    """
    clone = HAEIMDampedMiner(
        eu=miner.eu, inv_table=miner.inv_table, cu=miner.cu,
        sound=getattr(miner, "sound", True),
    )
    batch = [
        (tid, [(it, q) for it, q in tmap.items()])
        for tid, tmap in sorted(miner.transactions.items())
    ]
    if batch:
        clone.bulk_construction(batch)
    return clone


def build_miner(ds: StreamDataset) -> HAEIMDampedMiner:
    """Dựng miner từ một bộ dữ liệu (không nạp sẵn, caller tự quyết định)."""
    return HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu)


@dataclass(slots=True)
class BenchmarkRow:
    """Một dòng kết quả đo: cùng một luồng, chạy 2 phương án."""

    label: str
    n_transactions: int
    n_items: int
    pruned_ms: float
    exact_ms: float | None
    pruned_hits: int
    exact_hits: int | None
    speedup: float | None
    agreement: float | None
    sound: bool | None
    itemsets_examined: int | None
    join_attempts: int | None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "transactions": self.n_transactions,
            "items": self.n_items,
            "pruned_ms": self.pruned_ms,
            "exact_ms": self.exact_ms,
            "pruned_hits": self.pruned_hits,
            "exact_hits": self.exact_hits,
            "speedup": self.speedup,
            "agreement": self.agreement,
            "sound": self.sound,
            "itemsets_examined": self.itemsets_examined,
            "join_attempts": self.join_attempts,
        }


def _mine_pruned(ds: StreamDataset, f: float, minae: float) -> tuple[list[dict], float, dict]:
    m = build_miner(ds)
    m.bulk_construction(
        [(tid, [(it, q) for it, q in tmap.items()])
         for tid, tmap in sorted(ds.transactions.items())]
    )
    t0 = time.perf_counter()
    out = m.mine(f=f, minae=minae)
    elapsed = (time.perf_counter() - t0) * 1000
    return out["dhaeis"], elapsed, out.get("stats", {})


def run_benchmark(
    n_transactions: int = 200,
    n_items: int = 12,
    seed: int = 42,
    f: float = 0.8,
    minae: float = 0.2,
    with_exact: bool = True,
    max_items_per_tx: int = 6,
) -> dict:
    """Đo 1 cấu hình: thuật toán cắt tỉa vs duyệt tất cả tập mục (ground truth).

    Dùng **cùng một luồng** cho cả hai phương án -> so sánh công bằng.
    Ground truth chỉ chạy được khi giỏ hàng không quá lớn (2^|Tj| tập mục con);
    nếu vượt ngưỡng, báo `exact_skipped` thay vì làm treo server.
    """
    ds = generate_stream(n_transactions, n_items, seed=seed,
                         min_items_per_tx=2, max_items_per_tx=max_items_per_tx,
                         name=f"bench_{n_transactions}x{n_items}")
    dhaeis, pruned_ms, stats = _mine_pruned(ds, f, minae)

    row = {
        "transactions": ds.n_transactions,
        "items": ds.n_items,
        "seed": seed,
        "f": f,
        "minae": minae,
        "pruned_ms": round(pruned_ms, 3),
        "pruned_hits": len(dhaeis),
        "join_attempts": stats.get("join_attempts"),
        "join_success": stats.get("join_success"),
        "pruned_stdaeub": stats.get("pruned_stdaeub"),
    }

    if with_exact:
        try:
            exact = exact_mine(ds.transactions, ds.eu, ds.inv_table, f, minae)
            cmp = compare_with_exact([d["pattern"] for d in dhaeis], exact)
            row.update(
                {
                    "exact_ms": exact.elapsed_ms,
                    "exact_hits": len(exact.dhaeis),
                    "itemsets_examined": exact.itemsets_examined,
                    "speedup": round(exact.elapsed_ms / pruned_ms, 2) if pruned_ms > 0 else None,
                    "agreement": cmp["agreement"],
                    "sound": cmp["sound"],
                    "complete": cmp["complete"],
                    "missing": cmp["missing"],
                    "extra": cmp["extra"],
                }
            )
        except ValueError as exc:
            row["exact_skipped"] = str(exc)
    return row


def run_scalability(
    sizes: list[dict] | None = None,
    f: float = 0.8,
    minae: float = 0.2,
    seed: int = 42,
    with_exact: bool = True,
    max_items_per_tx: int = 10,
) -> dict:
    """Quét nhiều cấu hình kích thước -> số liệu vẽ đồ thị scalability.

    `sizes`: danh sách {"transactions": n, "items": m}. Mặc định dùng bộ cố định
    để kết quả tái lập được (đưa thẳng vào phụ lục luận văn).

    `max_items_per_tx` quyết định độ lớn của ground truth (O(Σ2^|T_j|)) — dùng
    giỏ hàng thực tế (8-12 mục) để thấy rõ lợi thế của cắt tỉa.
    """
    if not sizes:
        sizes = [
            {"transactions": 50, "items": 8},
            {"transactions": 100, "items": 10},
            {"transactions": 200, "items": 12},
            {"transactions": 400, "items": 14},
            {"transactions": 800, "items": 16},
        ]
    rows: list[dict] = []
    for s in sizes:
        row = run_benchmark(
            n_transactions=int(s.get("transactions", 100)),
            n_items=int(s.get("items", 10)),
            seed=int(s.get("seed", seed)),
            f=f,
            minae=minae,
            with_exact=with_exact,
            max_items_per_tx=int(s.get("max_items_per_tx", max_items_per_tx)),
        )
        rows.append(row)
    return {
        "f": f,
        "minae": minae,
        "max_items_per_tx": max_items_per_tx,
        "rows": rows,
        "note": "exact_ms = duyệt tất cả tập mục (ground truth); "
                "pruned_ms = HAEIM_Damped có cắt tỉa",
    }


def run_sweep(
    miner: HAEIMDampedMiner,
    f_values: list[float] | None = None,
    minae_values: list[float] | None = None,
) -> dict:
    """Quét tham số (f, minae) trên luồng hiện tại -> đường cong độ nhạy.

    Chạy trên **bản sao** miner nên không ảnh hưởng kết quả đang hiển thị.
    """
    if not f_values:
        f_values = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    if not minae_values:
        minae_values = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4]
    f_values = sorted({round(float(x), 6) for x in f_values})
    minae_values = sorted({round(float(x), 6) for x in minae_values})

    clone = clone_miner(miner)
    rows: list[dict] = []
    for f in f_values:
        for minae in minae_values:
            t0 = time.perf_counter()
            out = clone.mine(f=f, minae=minae)
            ms = (time.perf_counter() - t0) * 1000
            hits = out["dhaeis"]
            rows.append(
                {
                    "f": f,
                    "minae": minae,
                    "count": len(hits),
                    "max_sdae": round(max((h["sdae"] for h in hits), default=0.0), 4),
                    "mean_sdae": round(
                        sum(h["sdae"] for h in hits) / len(hits), 4
                    ) if hits else 0.0,
                    "elapsed_ms": round(ms, 3),
                    "cached": bool(out.get("cached")),
                }
            )
    return {
        "f_values": f_values,
        "minae_values": minae_values,
        "rows": rows,
        "note": "Độ nhạy của số lượng HAEI theo hệ số suy giảm f và ngưỡng minae",
    }


def run_pruning_comparison(
    n_transactions: int = 1000,
    n_items: int = 18,
    max_items_per_tx: int = 12,
    seed: int = 42,
    f: float = 0.8,
    minae: float = 0.2,
) -> dict:
    """So sánh 2 chiến lược cắt tỉa trên CÙNG một luồng, đối chiếu ground truth.

    | chiến lược | cận trên dùng để cắt            | đặc tính        |
    |------------|----------------------------------|-----------------|
    | `sound`    | cận trên ÂM (đúng cho mọi mở rộng) | **không bỏ sót** |
    | `legacy`   | cận trên 1-phần-mở-rộng (PDF)     | nhanh hơn, **bỏ sót** |

    Kết quả là bảng số liệu chính cho luận văn: đánh đổi giữa tốc độ và độ
    đúng, có định lượng cụ thể (số HAEI bỏ sót, tỉ lệ khớp, hệ số thời gian).
    """
    ds = generate_stream(
        n_transactions, n_items, seed=seed,
        min_items_per_tx=2, max_items_per_tx=max_items_per_tx,
        name=f"prune_cmp_{n_transactions}x{n_items}",
    )
    batch = [
        (tid, [(it, q) for it, q in tmap.items()])
        for tid, tmap in sorted(ds.transactions.items())
    ]

    def _run(sound: bool) -> tuple[list[dict], float]:
        m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu, sound=sound)
        m.bulk_construction(batch)
        t0 = time.perf_counter()
        out = m.mine(f=f, minae=minae)
        return out["dhaeis"], (time.perf_counter() - t0) * 1000

    truth = exact_mine(ds.transactions, ds.eu, ds.inv_table, f, minae)
    rows = []
    for label, sound in (("sound", True), ("legacy", False)):
        dhaeis, ms = _run(sound)
        cmp = compare_with_exact([d["pattern"] for d in dhaeis], truth)
        rows.append({
            "strategy": label,
            "description": (
                "cận trên ÂM — cắt tỉa an toàn, khớp 100% ground truth"
                if sound else
                "cận trên 1-phần-mở-rộng (theo PDF) — nhanh hơn nhưng bỏ sót HAEI"
            ),
            "elapsed_ms": round(ms, 2),
            "hits": cmp["pruned_count"],
            "exact_hits": cmp["exact_count"],
            "agreement": cmp["agreement"],
            "sound": cmp["sound"],
            "missing": cmp["missing"],
            "extra": cmp["extra"],
        })
    sound_row, legacy_row = rows
    return {
        "f": f,
        "minae": minae,
        "transactions": ds.n_transactions,
        "items": ds.n_items,
        "max_items_per_tx": max_items_per_tx,
        "seed": seed,
        "rows": rows,
        "exact_ms": truth.elapsed_ms,
        "itemsets_examined": truth.itemsets_examined,
        "speedup_sound_vs_legacy": (
            round(legacy_row["elapsed_ms"] / sound_row["elapsed_ms"], 2)
            if sound_row["elapsed_ms"] > 0 else None
        ),
        "speedup_sound_vs_exact": (
            round(truth.elapsed_ms / sound_row["elapsed_ms"], 2)
            if sound_row["elapsed_ms"] > 0 else None
        ),
        "missed_by_legacy": max(0, legacy_row["exact_hits"] - legacy_row["hits"]),
    }


def measure_construction_cost(
    n_transactions: int = 200,
    n_items: int = 12,
    seed: int = 42,
    repeats: int = 3,
) -> dict:
    """Đo chi phí Pha 1 (Construction) — kiểm chứng tính chất O(|T_j|).

    Nếu Construction là O(|T_j|) thì thời gian xử lý mỗi giao dịch phải
    **gần như không đổi** theo độ dài luồng (không quét lại dữ liệu cũ).

    Kỹ thuật đo: warm-up (loại ảnh hưởng khởi tạo) + best-of-N (lấy lần chạy
    nhanh nhất) — tránh nhiễu của trình đo vi mô.
    """
    ds = generate_stream(n_transactions, n_items, seed=seed, name="construction_bench")
    batch = [
        (tid, [(it, q) for it, q in tmap.items()])
        for tid, tmap in sorted(ds.transactions.items())
    ]

    # warm-up: chạy trước vài giao dịch để bộ đệm/allocator ổn định
    warm = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu)
    for tid, items in batch[: min(20, len(batch))]:
        warm.construction(tid, items)

    best_run: list[float] | None = None
    for _ in range(max(1, repeats)):
        m = build_miner(ds)
        per_tx_ms: list[float] = []
        for tid, items in batch:
            t0 = time.perf_counter()
            m.construction(tid, items)
            per_tx_ms.append((time.perf_counter() - t0) * 1000)
        if best_run is None or sum(per_tx_ms) < sum(best_run):
            best_run = per_tx_ms
    per_tx_ms = best_run or []

    # nạp hàng loạt -> so sánh tổng
    m2 = build_miner(ds)
    t0 = time.perf_counter()
    m2.bulk_construction(batch)
    bulk_ms = (time.perf_counter() - t0) * 1000

    half = len(per_tx_ms) // 2 or 1
    first_half = per_tx_ms[:half] or per_tx_ms
    second_half = per_tx_ms[half:] or per_tx_ms
    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)
    return {
        "transactions": n_transactions,
        "items": n_items,
        "total_ms": round(sum(per_tx_ms), 3),
        "avg_ms_first_half": round(avg_first, 4),
        "avg_ms_second_half": round(avg_second, 4),
        # hệ số phình to ~1 nghĩa là không quét lại (O(|T_j|) thuần)
        "growth_ratio": round(avg_second / avg_first, 3) if avg_first > 0 else None,
        "bulk_ms": round(bulk_ms, 3),
        "bulk_speedup": round(sum(per_tx_ms) / bulk_ms, 2) if bulk_ms > 0 else None,
        "per_tx_ms": [round(x, 4) for x in per_tx_ms],
    }
