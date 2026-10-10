"""FastAPI backend HAEIM_Damped — bám sát PDF TongHop_LuongXuLy_HAEIM_Damped.pdf.

Luồng 3 pha:
  POST /api/transactions  -> Pha 1 Construction (streaming, O(|T_j|))
  POST /api/mine          -> Pha 2 Restructure + Pha 3 Expansion (DFS)
  GET  /api/results       -> tập DHAEIs gần nhất
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from .schemas import MineRequest, NewTransaction
from .core.data import CU, DEFAULT_F, DEFAULT_MINAE, EU, INV, EXAMPLE_STREAM
from .core.haeim_damped import HAEIMDampedMiner

app = FastAPI(title="HAEIM_Damped Backend", version="1.0.0",
              description="Backend khai thác tập mục hiệu suất trung bình cao trên luồng suy giảm (3 pha: Construction/Restructure/Expansion).")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

miner = HAEIMDampedMiner(eu=EU, inv_table=INV)
miner.load_example_stream()  # nạp sẵn Bảng 1 để demo đúng ví dụ PDF


@app.get("/")
def root():
    return {"service": "HAEIM_Damped", "ltid": miner.ltid,
            "transactions": len(miner.transactions),
            "default": {"f": DEFAULT_F, "minae": DEFAULT_MINAE}}


@app.get("/api/config")
def get_config():
    """Bảng chi phí đầu tư, ngoại tiện ích và tham số mặc định (Bảng 2 + §2)."""
    return {"eu": EU, "cu": CU, "inv": INV,
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
    if not body.items:
        raise HTTPException(400, "Transaction rỗng")
    for it in body.items:
        if it.item not in miner.eu:
            raise HTTPException(400, f"item '{it.item}' chưa có trong EU/INV (a..f)")
    miner.construction(tid, [(it.item, it.qty) for it in body.items])
    node_info = {",".join(k): len(v.entries) for k, v in miner.nodes.items() if len(k) == 1}
    return {"tid": tid, "ltid": miner.ltid, "singleton_entry_counts": node_info}


@app.post("/api/mine")
def mine(body: MineRequest):
    """Pha 2 Restructure + Pha 3 Expansion. Không quét lại luồng gốc."""
    if not miner.transactions:
        raise HTTPException(400, "Luồng rỗng")
    return miner.mine(f=body.f, minae=body.minae)


@app.get("/api/results")
def get_results():
    return {"ltid": miner.ltid, "dhaeis": miner.results}


@app.get("/api/dae-lists")
def dae_lists():
    """Soát DAE-List toàn cục (cấp cửa sổ + entries cấp giao dịch thô)."""
    out = []
    for key in sorted(miner.nodes):
        n = miner.nodes[key]
        out.append({"pattern": list(n.pattern), "inv": n.inv,
                    "sdae": round(n.sdae, 4), "smdaeub": round(n.smdaeub, 4),
                    "stdaeub": round(n.stdaeub, 4),
                    "entries": [{"tid": e.tid, "u": e.u, "ae": round(e.ae, 4),
                                 "maeub": round(e.maeub, 4), "dae": round(e.dae, 4),
                                 "mdaeub": round(e.mdaeub, 4), "tdaeub": round(e.tdaeub, 4),
                                 "maxru": e.maxru, "minInv": e.min_inv, "k": e.k}
                                for e in sorted(n.entries, key=lambda x: x.tid)]})
    return {"order": miner.order, "nodes": out}


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
