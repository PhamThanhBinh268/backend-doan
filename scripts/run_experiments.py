"""Chạy toàn bộ thực nghiệm và ghi kết quả ra file (tái lập được cho luận văn).

Cách dùng:
    python scripts/run_experiments.py            # ghi ra docs/results/
    python scripts/run_experiments.py --quick    # bản rút gọn (vài giây)

Kết quả ghi ra:
    docs/results/experiments.json   — dữ liệu thô (máy đọc được)
    docs/results/experiments.md     — bảng số liệu dạng Markdown (đưa vào báo cáo)

Tất cả thí nghiệm đều **tất định** (seed cố định) nên chạy lại cho kết quả y hệt.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.baseline import compare_with_exact, exact_mine          # noqa: E402
from app.core.bench import (                                          # noqa: E402
    measure_construction_cost,
    run_benchmark,
    run_pruning_comparison,
    run_scalability,
    run_sweep,
)
from app.core.datasets import generate_stream                          # noqa: E402
from app.core.haeim_damped import HAEIMDampedMiner                    # noqa: E402

OUT_DIR = ROOT / "docs" / "results"
F, MINAE = 0.8, 0.2


def _mine(ds, sound=True):
    m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu, sound=sound)
    m.bulk_construction(
        [(tid, sorted(t.items())) for tid, t in sorted(ds.transactions.items())]
    )
    t0 = time.perf_counter()
    out = m.mine(f=F, minae=MINAE)
    return out, (time.perf_counter() - t0) * 1000


def exp1_accuracy(quick: bool) -> dict:
    """Độ đúng: cắt tỉa âm vs ground truth trên nhiều cấu hình."""
    cases = [
        (100, 6, 4), (200, 8, 6), (500, 12, 8), (1000, 18, 12), (2000, 20, 12),
    ] if not quick else [(200, 8, 6), (1000, 18, 12)]
    rows = []
    for ntx, nitems, maxb in cases:
        ds = generate_stream(ntx, nitems, seed=42, min_items_per_tx=2, max_items_per_tx=maxb)
        out, ms = _mine(ds, sound=True)
        truth = exact_mine(ds.transactions, ds.eu, ds.inv_table, F, MINAE)
        cmp = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)
        rows.append({
            "transactions": ntx, "items": nitems, "max_items_per_tx": maxb,
            "haei_pruned": cmp["pruned_count"], "haei_exact": cmp["exact_count"],
            "agreement": cmp["agreement"], "sound": cmp["sound"],
            "missing": cmp["missing"], "pruned_ms": round(ms, 2),
            "exact_ms": truth.elapsed_ms, "itemsets_examined": truth.itemsets_examined,
            "speedup": round(truth.elapsed_ms / ms, 2) if ms else None,
        })
    return {"title": "Độ đúng: HAEIM_Damped (cắt tỉa âm) vs ground truth", "rows": rows}


def exp2_pruning(quick: bool) -> dict:
    """Đánh đổi: cắt tỉa âm (an toàn) vs bản PDF (nhanh, bỏ sót)."""
    cases = [(1000, 18, 12)] if quick else [(500, 14, 10), (1000, 18, 12), (2000, 20, 14)]
    rows = []
    for ntx, nitems, maxb in cases:
        r = run_pruning_comparison(ntx, nitems, maxb, 42, F, MINAE)
        rows.append({
            "transactions": ntx, "items": nitems, "max_items_per_tx": maxb,
            "sound_ms": r["rows"][0]["elapsed_ms"], "sound_hits": r["rows"][0]["hits"],
            "legacy_ms": r["rows"][1]["elapsed_ms"], "legacy_hits": r["rows"][1]["hits"],
            "exact_hits": r["rows"][0]["exact_hits"],
            "legacy_missing": r["rows"][1]["missing"],
            "sound_agreement": r["rows"][0]["agreement"],
            "legacy_agreement": r["rows"][1]["agreement"],
            "exact_ms": r["exact_ms"],
        })
    return {"title": "So sánh 2 chiến lược cắt tỉa", "rows": rows}


def exp3_scaling(quick: bool) -> dict:
    """Quét kích thước luồng (giỏ hàng thực tế 10 mục → thấy lợi thế mũ cấp)."""
    sizes = ([{"transactions": 100, "items": 8}, {"transactions": 300, "items": 12},
              {"transactions": 600, "items": 14}] if quick else
             [{"transactions": 100, "items": 8}, {"transactions": 200, "items": 10},
              {"transactions": 400, "items": 12}, {"transactions": 800, "items": 14},
              {"transactions": 1600, "items": 16}])
    r = run_scalability(sizes, f=F, minae=MINAE, with_exact=True, max_items_per_tx=10)
    return {"title": "Khả năng mở rộng (scalability) — giỏ hàng tối đa 10 mục",
            "rows": r["rows"]}


def exp4_sweep(quick: bool) -> dict:
    """Độ nhạy theo f và minae trên luồng cố định."""
    ds = generate_stream(1000, 18, seed=42, min_items_per_tx=2, max_items_per_tx=10)
    m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu)
    m.bulk_construction([(tid, sorted(t.items())) for tid, t in sorted(ds.transactions.items())])
    r = run_sweep(m, [0.6, 0.7, 0.8, 0.9], [0.05, 0.1, 0.2, 0.3, 0.4])
    return {"title": "Độ nhạy theo tham số f / minae", "rows": r["rows"]}


def exp5_construction(quick: bool) -> dict:
    """Chi phí Pha 1 — kiểm chứng O(|T_j|)."""
    r = measure_construction_cost(600 if not quick else 200, 12, 42)
    r.pop("per_tx_ms", None)
    return {"title": "Chi phí Pha 1 (Construction) — kiểm chứng O(|T_j|)", "rows": [r]}


def to_markdown(data: dict) -> str:
    out = ["# Kết quả thực nghiệm (sinh tự động)", "",
           f" Máy: {data['env']['platform']} · Python {data['env']['python']} · "
           f"f={F} · minae={MINAE} · ngày {data['env']['date']}", ""]
    for exp in data["experiments"]:
        out.append(f"## {exp['title']}")
        out.append("")
        rows = exp["rows"]
        if not rows:
            out.append("_không có dữ liệu_")
            out.append("")
            continue
        cols = list(rows[0].keys())
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "|".join("---" for _ in cols) + "|")
        for r in rows:
            out.append("| " + " | ".join(
                (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v))
                for v in r.values()) + " |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    quick = "--quick" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    exps = [
        exp1_accuracy(quick),
        exp2_pruning(quick),
        exp3_scaling(quick),
        exp4_sweep(quick),
        exp5_construction(quick),
    ]
    data = {
        "env": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "date": time.strftime("%Y-%m-%d"),
            "quick": quick,
        },
        "params": {"f": F, "minae": MINAE},
        "experiments": exps,
    }
    (OUT_DIR / "experiments.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "experiments.md").write_text(to_markdown(data), encoding="utf-8")
    print(f"Đã ghi {OUT_DIR/'experiments.json'} và {OUT_DIR/'experiments.md'} "
          f"({time.perf_counter()-t0:.1f}s)")
    for exp in exps:
        print(f"  - {exp['title']}: {len(exp['rows'])} dòng")


if __name__ == "__main__":
    main()
