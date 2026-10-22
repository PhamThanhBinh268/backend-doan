"""FastAPI backend HAEIM_Damped — bám sát PDF TongHop_LuongXuLy_HAEIM_Damped.pdf.

Luồng 3 pha:
  POST /api/transactions  -> Pha 1 Construction (streaming, O(|T_j|))
  POST /api/mine          -> Pha 2 Restructure + Pha 3 Expansion (DFS)
  GET  /api/results       -> tập DHAEIs gần nhất

Nhóm chức năng mở rộng (phục vụ chương "Thực nghiệm" của luận văn):
  /api/validate      -> kiểm chứng thuật toán cắt tỉa so với ground truth
  /api/bench, /api/scalability, /api/sweep, /api/construction-cost
  /api/datasets, /api/dataset/*  -> bộ dữ liệu (CSV / bộ sinh tổng hợp)
  /api/explain       -> truy vết "vì sao" cho một pattern
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .schemas import (
    BenchRequest,
    BulkTransactions,
    ConstructionCostRequest,
    ExplainRequest,
    GenerateDatasetRequest,
    ImportCsvRequest,
    LoadDatasetRequest,
    MineRequest,
    NewItem,
    NewTransaction,
    PruningComparisonRequest,
    ScalabilityRequest,
    SweepRequest,
    ValidateRequest,
)
from .core.data import CU, DEFAULT_F, DEFAULT_MINAE, EU, INV, EXAMPLE_STREAM
from .core.haeim_damped import HAEIMDampedMiner
from .core import bench as bench_mod
from .core import datasets as ds_mod
from .core import explain as explain_mod
from .core.baseline import compare_with_exact, exact_mine

START_TIME = time.time()

app = FastAPI(title="HAEIM_Damped Backend", version="2.1.0",
              description="Backend khai thác tập mục hiệu suất trung bình cao trên luồng suy giảm "
                          "(3 pha: Construction/Restructure/Expansion) kèm mô hình kiểm chứng "
                          "độ đúng và bộ công cụ đo đạc hiệu năng.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

miner = HAEIMDampedMiner(eu=EU, inv_table=INV, cu=CU)
miner.load_example_stream()  # nạp sẵn Bảng 1 để demo đúng ví dụ PDF


def _allocate_bulk_tids(
    body: BulkTransactions, used: set[int], start: int
) -> list[tuple[int, list[tuple[str, float]]]]:
    """Gán tid cho cả lô bulk, xử lý chặt va chạm auto/explicit.

    - explicit trùng nhau hoặc trùng luồng cũ -> 400 (đã check ở layer gọi,
      đây là chốt chặn cuối).
    - auto: cấp từ `start` trở đi, bỏ qua mọi tid đã dùng (luồng cũ +
      explicit trong lô + auto đã cấp).
    """
    explicit = {t.tid for t in body.transactions if t.tid is not None}
    taken = set(used) | explicit
    nxt = start
    batch: list[tuple[int, list[tuple[str, float]]]] = []
    for t in body.transactions:
        if t.tid is not None:
            tid = t.tid
        else:
            while nxt in taken:
                nxt += 1
            tid = nxt
            taken.add(tid)
            nxt += 1
        batch.append((tid, [(it.item, it.qty) for it in t.items]))
    return batch


@app.get("/")
def root():
    return {"service": "HAEIM_Damped", "ltid": miner.ltid,
            "transactions": len(miner.transactions),
            "items": len(miner.eu),
            "version": miner.version,
            "last_stats": miner.last_stats,
            "uptime_s": round(time.time() - START_TIME, 1),
            "default": {"f": DEFAULT_F, "minae": DEFAULT_MINAE}}


@app.get("/api/health")
def health():
    """Trạng thái sức khỏe của backend (healthcheck / nâng cấp vận hành).

    Trả về trạng thái nền tảng: service alive, luồng hiện tại, phiên bản miner.
    Dùng cho monitoring/healthcheck khi triển khai production.
    """
    return {
        "status": "ok",
        "service": "HAEIM_Damped",
        "transactions": len(miner.transactions),
        "ltid": miner.ltid,
        "items": len(miner.eu),
        "version": miner.version,
        "uptime_s": round(time.time() - START_TIME, 1),
    }


@app.get("/api/config")
def get_config():
    """Bảng chi phí đầu tư, ngoại tiện ích và tham số mặc định (Bảng 2 + §2)."""
    cu = dict(CU)
    cu.update(miner.cu)
    return {"eu": dict(miner.eu), "cu": cu, "inv": dict(miner.inv_table),
            "default_f": DEFAULT_F, "default_minae": DEFAULT_MINAE,
            "ltid": miner.ltid}


@app.get("/api/transactions")
def list_transactions():
    return {"ltid": miner.ltid,
            "transactions": [{"tid": tid, "items": [{"item": k, "qty": v} for k, v in sorted(m.items())]}
                              for tid, m in sorted(miner.transactions.items())]}


@app.post("/api/transactions")
def add_transaction(body: NewTransaction):
    """Pha 1 Construction: ghi nhận T_j mới (u, ae thô, MAEUB thô)."""
    tid = body.tid if body.tid is not None else (miner.ltid + 1)
    if tid in miner.transactions:
        raise HTTPException(400, f"tid {tid} đã tồn tại")
    for it in body.items:
        if it.item not in miner.eu:
            raise HTTPException(
                400,
                f"item '{it.item}' chưa có trong EU/INV — "
                "đăng ký trước qua POST /api/items",
            )
    try:
        miner.construction(tid, [(it.item, it.qty) for it in body.items])
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    singleton_counts = {",".join(k): len(v.entries) for k, v in miner.nodes.items()}
    return {"tid": tid, "ltid": miner.ltid, "singleton_entry_counts": singleton_counts}


@app.post("/api/transactions/bulk")
def add_transactions_bulk(body: BulkTransactions):
    """Nạp hàng loạt nhiều T_j trong 1 request (giảm round-trip streaming)."""
    if not body.transactions:
        raise HTTPException(400, "Danh sách rỗng")
    seen: set[int] = set()
    for t in body.transactions:
        if t.tid is not None:
            if t.tid in seen:
                raise HTTPException(400, f"tid {t.tid} lặp trong batch")
            seen.add(t.tid)
            if t.tid in miner.transactions:
                raise HTTPException(400, f"tid {t.tid} đã tồn tại")
        for it in t.items:
            if it.item not in miner.eu:
                raise HTTPException(400, f"item '{it.item}' chưa đăng ký qua POST /api/items")
    try:
        batch = _allocate_bulk_tids(body, set(miner.transactions), miner.ltid + 1)
        tids = miner.bulk_construction(batch)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {"tids": tids, "ltid": miner.ltid, "loaded": len(tids)}


@app.post("/api/items")
def register_item(body: NewItem):
    """Đăng ký item mới phát sinh trên luồng (ngoài a..f của Bảng 2)."""
    try:
        miner.register_item(body.item, body.eu, body.inv, body.cu)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"item": body.item, "eu": miner.eu[body.item],
            "inv": miner.inv_table[body.item],
            "cu": miner.cu.get(body.item)}


@app.post("/api/mine")
def mine(body: MineRequest):
    """Pha 2 Restructure + Pha 3 Expansion. Không quét lại luồng gốc."""
    # Chọn chiến lược cắt tỉa: âm (mặc định, an toàn) hay bản PDF (nhanh hơn).
    miner.sound = body.sound
    try:
        return miner.mine(f=body.f, minae=body.minae)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/results")
def get_results():
    return {"ltid": miner.ltid, "dhaeis": miner.results}


@app.get("/api/dae-lists")
def dae_lists():
    """Soát DAE-List toàn cục (singleton + pattern dài từ Expansion gần nhất)."""
    combined: dict[tuple, object] = dict(miner.nodes)
    combined.update(miner.extra_nodes)
    out = []
    for key in sorted(combined):
        n = combined[key]
        # Pattern dài sinh ra ở Expansion không có cận "kiểu PDF" (chỉ tính khi
        # hiển thị) → tính bù tại đây.
        if not n.entries or n.entries[0].tdaeub == 0.0:
            miner.compute_paper_bounds(n)
        out.append({"pattern": list(n.pattern), "inv": n.inv,
                    "sdae": round(n.sdae, 4), "smdaeub": round(n.smdaeub, 4),
                    "stdaeub": round(n.stdaeub, 4),
                    # cận trên ÂM — dùng để cắt tỉa an toàn ở Pha 2/3
                    "sound_bound": round(n.sbound, 4),
                    "entries": [{"tid": e.tid, "u": e.u, "ae": round(e.ae, 4),
                                 "maeub": round(e.maeub, 4), "dae": round(e.dae, 4),
                                 "mdaeub": round(e.mdaeub, 4), "tdaeub": round(e.tdaeub, 4),
                                 "sound_bound": round(e.sbnd, 6),
                                 "maxru": e.maxru, "minInv": e.min_inv, "k": e.k}
                                for e in sorted(n.entries, key=lambda x: x.tid)]})
    return {"order": list(miner.order), "nodes": out, "sound_mode": miner.sound}


@app.post("/api/load-example")
def load_example():
    """Nạp lại luồng mẫu Bảng 1 (8 giao dịch)."""
    miner.load_example_stream()
    return {"loaded": len(miner.transactions), "ltid": miner.ltid}


@app.post("/api/reset")
def reset():
    miner.reset()
    return {"ok": True}


@app.get("/api/example-stream")
def example_stream():
    return {"stream": {str(t): [{"item": i, "qty": q} for i, q in v] for t, v in EXAMPLE_STREAM.items()},
            "eu": EU, "cu": CU, "inv": INV}


@app.get("/ui", include_in_schema=False)
def ui():
    """Trang test frontend đơn giản."""
    p = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    if not p.exists():
        raise HTTPException(404, "frontend/index.html chưa có")
    return FileResponse(str(p), media_type="text/html")


# ============================================================================
# NHÓM 2: KIỂM CHỨNG ĐỘ ĐÚNG (ground truth) — chương "Đánh giá độ đúng"
# ============================================================================
@app.post("/api/validate")
def validate(body: ValidateRequest):
    """Đối chiếu thuật toán cắt tỉa với ground truth (duyệt tất cả tập mục).

    Chạy trên **luồng hiện tại** của miner. Kết quả cho biết phép cắt tỉa có
    an toàn không (không bỏ sót HAEI) và có sinh thừa không.
    """
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng — hãy nạp dữ liệu trước")
    try:
        pruned = miner.mine(f=body.f, minae=body.minae)
        truth = exact_mine(
            miner.transactions, miner.eu, miner.inv_table,
            f=body.f, minae=body.minae, max_tx_items=body.max_tx_items,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    cmp = compare_with_exact([d["pattern"] for d in pruned["dhaeis"]], truth)
    return {
        "f": body.f,
        "minae": body.minae,
        "transactions": truth.transactions,
        "items": truth.items,
        "pruned": {
            "count": len(pruned["dhaeis"]),
            "elapsed_ms": pruned["stats"].get("elapsed_ms"),
            "join_attempts": pruned["stats"].get("join_attempts"),
        },
        "exact": {
            "count": len(truth.dhaeis),
            "elapsed_ms": truth.elapsed_ms,
            "itemsets_examined": truth.itemsets_examined,
        },
        "speedup": (
            round(truth.elapsed_ms / pruned["stats"]["elapsed_ms"], 2)
            if pruned["stats"].get("elapsed_ms") else None
        ),
        **cmp,
    }


# ============================================================================
# NHÓM 3: ĐO ĐẠC HIỆU NĂNG — chương "Kết quả thực nghiệm"
# ============================================================================
@app.post("/api/bench")
def bench(body: BenchRequest):
    """Đo 1 cấu hình: HAEIM_Damped (có cắt tỉa) vs duyệt tất cả tập mục."""
    try:
        return bench_mod.run_benchmark(
            n_transactions=body.n_transactions,
            n_items=body.n_items,
            seed=body.seed,
            f=body.f,
            minae=body.minae,
            with_exact=body.with_exact,
            max_items_per_tx=body.max_items_per_tx,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/pruning-comparison")
def pruning_comparison(body: PruningComparisonRequest):
    """So sánh cắt tỉa ÂM (an toàn) vs bản PDF (nhanh, bỏ sót) — có ground truth."""
    try:
        return bench_mod.run_pruning_comparison(
            n_transactions=body.n_transactions,
            n_items=body.n_items,
            max_items_per_tx=body.max_items_per_tx,
            seed=body.seed,
            f=body.f,
            minae=body.minae,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/scalability")
def scalability(body: ScalabilityRequest):
    """Quét nhiều cấu hình kích thước luồng -> số liệu vẽ đồ thị scalability."""
    try:
        return bench_mod.run_scalability(
            sizes=body.sizes,
            f=body.f,
            minae=body.minae,
            seed=body.seed,
            with_exact=body.with_exact,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sweep")
def sweep(body: SweepRequest):
    """Quét tham số f / minae trên luồng hiện tại -> đường cong độ nhạy."""
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng — hãy nạp dữ liệu trước")
    try:
        return bench_mod.run_sweep(miner, body.f_values, body.minae_values)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/construction-cost")
def construction_cost(body: ConstructionCostRequest):
    """Đo chi phí Pha 1 (Construction) — kiểm chứng tính chất O(|T_j|)."""
    try:
        return bench_mod.measure_construction_cost(
            n_transactions=body.n_transactions,
            n_items=body.n_items,
            seed=body.seed,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ============================================================================
# NHÓM 4: BỘ DỮ LIỆU
# ============================================================================
@app.get("/api/datasets")
def datasets():
    """Danh sách bộ dữ liệu dựng sẵn + bộ sinh tổng hợp mặc định."""
    return {"datasets": ds_mod.list_datasets()}


@app.post("/api/dataset/load")
def dataset_load(body: LoadDatasetRequest):
    """Nạp một bộ dữ liệu dựng sẵn (thay thế luồng hiện tại)."""
    try:
        ds = ds_mod.load_dataset(body.key)
        n = miner.load_dataset(ds.transactions, ds.eu, ds.inv_table, ds.cu)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"loaded": n, "dataset": ds.summary(), "ltid": miner.ltid}


@app.post("/api/dataset/generate")
def dataset_generate(body: GenerateDatasetRequest):
    """Sinh luồng giao dịch tổng hợp (mô phỏng siêu thị) — tất định theo seed."""
    try:
        ds = ds_mod.generate_stream(
            n_transactions=body.n_transactions,
            n_items=body.n_items,
            seed=body.seed,
            qty_max=body.qty_max,
            zipf_s=body.zipf_s,
            drift=body.drift,
            min_items_per_tx=body.min_items_per_tx,
            max_items_per_tx=body.max_items_per_tx,
            name=f"gen_{body.n_transactions}x{body.n_items}_s{body.seed}",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    out = {"dataset": ds.summary(),
           "sample": {str(t): [{"item": i, "qty": q} for i, q in sorted(ds.transactions[t].items())]
                      for t in sorted(ds.transactions)[:5]},
           "eu": ds.eu, "inv": ds.inv_table}
    if body.load:
        try:
            miner.load_dataset(ds.transactions, ds.eu, ds.inv_table, ds.cu)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        out["loaded"] = ds.n_transactions
        out["ltid"] = miner.ltid
    return out


@app.post("/api/dataset/import")
def dataset_import(body: ImportCsvRequest):
    """Nhập luồng giao dịch từ CSV (tid,item,qty)."""
    try:
        txs = ds_mod.parse_csv(body.csv)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    items = sorted({i for t in txs.values() for i in t})
    eu = body.eu or {i: 1.0 for i in items}
    cu = body.cu or {i: 1.0 for i in items}
    if body.inv:
        # Bảng INV do người dùng đưa vào phải phủ HẾT các mục — nếu thiếu thì
        # báo 400 (trước đây KeyError không bắt → HTTP 500).
        thieu_inv = [i for i in items if i not in body.inv]
        if thieu_inv:
            raise HTTPException(400, f"thiếu INV cho: {', '.join(thieu_inv)}")
        inv = {i: float(body.inv[i]) for i in items}
    else:
        # quy ước suy luận như Bảng 2 của PDF: Inv(i) = cu(i) * tổng_qty(i)
        inv = {
            i: round(cu.get(i, 1.0) * sum(t.get(i, 0.0) for t in txs.values()), 2)
            for i in items
        }
    missing = [i for i in items if i not in eu or i not in inv]
    if missing:
        raise HTTPException(400, f"thiếu EU/INV cho: {', '.join(missing)}")
    out = {"transactions": len(txs), "items": len(items)}
    if body.load:
        try:
            n = miner.load_dataset(txs, eu, inv, cu)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        out["loaded"] = n
        out["ltid"] = miner.ltid
    return out


@app.get("/api/export")
def export(fmt: str = Query("csv", pattern="^(csv|json)$")):
    """Xuất kết quả khai thác (DHAEIs) + luồng giao dịch ra CSV/JSON."""
    dhaeis = miner.results
    if fmt == "json":
        return {
            "ltid": miner.ltid,
            "dhaeis": dhaeis,
            "transactions": {
                str(tid): {i: q for i, q in sorted(t.items())}
                for tid, t in sorted(miner.transactions.items())
            },
            "eu": miner.eu,
            "inv": miner.inv_table,
        }
    lines = ["pattern,sdae,smdaeub,stdaeub"]
    for d in dhaeis:
        pat = "{" + ",".join(d["pattern"]) + "}"
        lines.append(f'"{pat}",{d["sdae"]},{d["smdaeub"]},{d["stdaeub"]}')
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv")


# ============================================================================
# NHÓM 5: GIẢI THÍCH KẾT QUẢ (phục vụ bảo vệ luận văn)
# ============================================================================
@app.get("/api/explain")
def explain(pattern: str = Query(..., description="Danh sách item, cách nhau bởi dấu phẩy"),
            f: float = Query(DEFAULT_F, gt=0, lt=1),
            minae: float = Query(DEFAULT_MINAE, ge=0)):
    """Giải thích một pattern: số liệu 3 pha + lý do kết luận."""
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng")
    items = [p.strip() for p in pattern.split(",") if p.strip()]
    if not items:
        raise HTTPException(400, "pattern rỗng")
    try:
        return explain_mod.explain_pattern(miner, items, f=f, minae=minae)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/explain/all")
def explain_all(f: float = Query(DEFAULT_F, gt=0, lt=1),
                minae: float = Query(DEFAULT_MINAE, ge=0)):
    """Giải thích toàn bộ DHAEIs của lần khai thác gần nhất."""
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng")
    return explain_mod.explain_all(miner, f=f, minae=minae)


@app.post("/api/explain")
def explain_post(body: ExplainRequest):
    """Giải thích một pattern (POST — tiện khi pattern dài)."""
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng")
    try:
        return explain_mod.explain_pattern(miner, body.pattern, f=body.f, minae=body.minae)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ============================================================================
# NHÓM 6: CHỈ SỐ VẬN HÀNH
# ============================================================================
@app.get("/api/metrics")
def metrics():
    """Chỉ số vận hành: quy mô DAE-List, số entry, kết quả gần nhất."""
    entries = sum(len(n.entries) for n in miner.nodes.values())
    extra = sum(len(n.entries) for n in miner.extra_nodes.values())
    return {
        "ltid": miner.ltid,
        "transactions": len(miner.transactions),
        "items": len(miner.eu),
        "singleton_nodes": len(miner.nodes),
        "singleton_entries": entries,
        "derived_nodes": len(miner.extra_nodes),
        "derived_entries": extra,
        "order": list(miner.order),
        "results": len(miner.results),
        "version": miner.version,
        "uptime_s": round(time.time() - START_TIME, 1),
        "last_stats": miner.last_stats,
    }


# ------------------------------------------------------------------ static UI
_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")
