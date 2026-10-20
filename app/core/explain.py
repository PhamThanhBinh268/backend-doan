"""Giải thích kết quả — truy vết "vì sao" cho từng pattern.

Khi bảo vệ luận văn, câu hỏi khó trả lời nhất là: *"Tại sao tập mục X bị loại
khỏi DHAEIs?"*. Module này dựng lại **vết đầy đủ** của một pattern qua cả 3 pha
để trả lời chính xác:

  Pha 1 Construction → u, ae thô, MAEUB thô trên từng giao dịch
  Pha 2 Restructure  → dae, MDAEUB, Sdae, SMDAEUB, STDAEUB (cận trên cắt tỉa)
  Pha 3 Expansion    → kết luận HAEI / bị cắt, và lý do cụ thể

Các "lý do" được sinh tự động từ đúng điều kiện trong mã nguồn, không hard-code:
  • `Sdae < minae`                      → hiệu suất trung bình chưa đủ ngưỡng
  • `SMDAEUB < minae`                   → bị lọc ngay ở Pha 2 (chưa từng vào DAE-List)
  • `STDAEUB(tiền tố) < minae`          → bị cắt cả nhánh ở Pha 3
  • `LTDAEUB < minae` khi ghép          → phép ghép bị dừng sớm
  • đạt đủ                             → HAEI
"""

from __future__ import annotations

from .haeim_damped import DAENode, DAEEntry, HAEIMDampedMiner

__all__ = ["explain_pattern", "explain_all"]


def _pattern_entries(
    miner: HAEIMDampedMiner,
    pattern: tuple[str, ...],
    f: float,
) -> tuple[DAENode, list[dict]]:
    """Dựng entry cấp giao dịch cho một pattern bất kỳ (kể cả pattern dài).

    - Singleton: pattern **đã có sẵn** trong DAE-List (`miner.nodes`) nên dùng
      luôn số liệu chuẩn của thuật toán (MAEUB/SMDAEUB/STDAEUB đúng như bảng
      Restructure). Tính lại từ luồng gốc sẽ ra SMDAEUB KHÁC (vì MAEUB ≠ eff)
      → dẫn tới lý do "bị lọc ở Pha 2" sai.
    - Pattern dài: nếu đã sinh ra ở Expansion (`miner.extra_nodes`) thì dùng luôn;
      nếu chưa, tính lại từ luồng gốc theo đúng Công thức 5.
    """
    missing = [i for i in pattern if i not in miner.eu]
    if missing:
        raise ValueError(f"item chưa đăng ký: {', '.join(missing)}")

    ltid = miner.ltid
    weights = miner._decay_weights(f, ltid)

    existing = miner.nodes.get(pattern) or miner.extra_nodes.get(pattern)
    if existing is not None:
        rows: list[dict] = []
        for e in existing.entries:
            tmap = miner.transactions.get(e.tid, {})
            rows.append(
                {
                    "tid": e.tid,
                    "qty": {i: tmap.get(i, 0.0) for i in pattern},
                    "u": round(e.u, 4),
                    "ae": round(e.ae, 6),
                    "eff": round(e.u / existing.inv, 6) if existing.inv else 0.0,
                    "maeub": round(e.maeub, 6),
                    "w": round(weights.get(e.tid, 0.0), 6),
                    "dae": round(e.dae, 6),
                    "mdaeub": round(e.mdaeub, 6),
                    "maxru": round(e.maxru, 4),
                    "min_inv": round(e.min_inv, 4),
                    "k": e.k,
                    "tdaeub": round(e.tdaeub, 6),
                }
            )
        return existing, rows

    node = DAENode(pattern=pattern, inv=miner.inv_of(pattern))
    rows = []
    sdae = 0.0
    smdaeub = 0.0
    plen = len(pattern)

    for tid in sorted(miner.transactions):
        tmap = miner.transactions[tid]
        if not all(i in tmap for i in pattern):
            continue
        u = sum(tmap[i] * miner.eu[i] for i in pattern)
        inv = node.inv
        ae = (u / (inv * plen)) if inv > 0 and plen else 0.0
        eff = (u / inv) if inv > 0 else 0.0
        w = weights.get(tid, 0.0)
        dae = ae * w
        mdaeub = eff * w
        sdae += dae
        smdaeub += mdaeub
        e = DAEEntry(tid=tid, u=u, ae=ae, maeub=eff, pu=0.0,
                     dae=dae, mdaeub=mdaeub)
        node.entries.append(e)
        rows.append(
            {
                "tid": tid,
                "qty": {i: tmap[i] for i in pattern},
                "u": round(u, 4),
                "ae": round(ae, 6),
                "eff": round(eff, 6),
                "w": round(w, 6),
                "dae": round(dae, 6),
                "mdaeub": round(mdaeub, 6),
            }
        )
    node.sdae = sdae
    node.smdaeub = smdaeub

    # Cận trên ÂM cho node này (nếu miner đang ở chế độ âm) — dùng để giải
    # thích đúng tiêu chí cắt tỉa thực sự đang áp dụng.
    if getattr(miner, "sound", True):
        try:
            miner._apply_sound_bounds(node, weights)
        except Exception:          # pragma: no cover - chỉ để truy vết không lỗi
            node.sbound = 0.0

    # maxru / minInv / k / TDAEUB — phụ thuộc thứ tự sau Restructure
    tx_sets = {tid: set(t) for tid, t in miner.transactions.items()}
    std = 0.0
    for e in node.entries:
        miner._fill_tight_fields(node, e, f, ltid, weights=weights, tx_sets=tx_sets)
        std += e.tdaeub
        for row in rows:
            if row["tid"] == e.tid:
                row["maxru"] = round(e.maxru, 4)
                row["min_inv"] = round(e.min_inv, 4)
                row["k"] = e.k
                row["tdaeub"] = round(e.tdaeub, 6)
    node.stdaeub = std
    return node, rows


def explain_pattern(
    miner: HAEIMDampedMiner,
    pattern,
    f: float = 0.8,
    minae: float = 0.2,
) -> dict:
    """Giải thích một pattern: số liệu đầy đủ + lý do kết luận."""
    pat = tuple(sorted(str(p).strip() for p in pattern if str(p).strip()))
    if not pat:
        raise ValueError("pattern rỗng")
    if not miner.transactions:
        raise ValueError("Luồng rỗng")

    # DAE-List phải khớp luồng + tham số hiện tại, nếu không order/order_index
    # còn cũ (hoặc rỗng) → STDAEUB/TDAEUB tính sai (vd gọi /api/explain khi
    # chưa chạy mine → mọi pattern ra STDAEUB = 0).
    miner.ensure_restructured(f, minae)

    node, rows = _pattern_entries(miner, pat, f)
    sdae = node.sdae
    is_haei = sdae >= minae

    reasons: list[dict] = []
    if is_haei:
        reasons.append(
            {
                "phase": "Pha 3",
                "code": "HAEI",
                "message": f"Sdae = {sdae:.4f} >= minae = {minae} → tập mục hiệu suất "
                           f"trung bình cao, đưa vào DHAEIs.",
            }
        )
    else:
        reasons.append(
            {
                "phase": "Pha 3",
                "code": "SDAE_LT_MINAE",
                "message": f"Sdae = {sdae:.4f} < minae = {minae} → không đạt ngưỡng, "
                           f"không phải HAEI.",
            }
        )

    # Nếu là singleton: nó có sống sót qua bộ lọc Pha 2 không?
    # Bộ lọc Restructure giữ node khi: SMDAEUB >= minae (bản thân có thể là
    # HAEI) HOẶC cận trên âm SBOUND >= minae (còn có thể sinh phần mở rộng là
    # HAEI). Chỉ khi CẢ HAI đều < minae thì node mới bị loại khỏi DAE-List.
    if len(pat) == 1:
        sbound = getattr(node, "sbound", 0.0)
        if node.smdaeub < minae and sbound < minae:
            reasons.append(
                {
                    "phase": "Pha 2",
                    "code": "SMDAEUB_LT_MINAE",
                    "message": f"SMDAEUB = {node.smdaeub:.4f} < minae = {minae} và cận trên "
                               f"âm SBOUND = {sbound:.4f} < minae → bị lọc ngay ở "
                               f"Restructure, không vào DAE-List ứng viên.",
                }
            )
        elif node.smdaeub < minae:
            reasons.append(
                {
                    "phase": "Pha 2",
                    "code": "SMDAEUB_LT_MINAE_SBOUND_GE",
                    "message": f"SMDAEUB = {node.smdaeub:.4f} < minae = {minae} nhưng cận "
                               f"trên âm SBOUND = {sbound:.4f} >= minae → vẫn giữ trong "
                               f"DAE-List vì còn có thể sinh phần mở rộng là HAEI.",
                }
            )
        else:
            reasons.append(
                {
                    "phase": "Pha 2",
                    "code": "SMDAEUB_GE_MINAE",
                    "message": f"SMDAEUB = {node.smdaeub:.4f} >= minae → qua được bộ lọc "
                               f"Restructure (đã vào DAE-List ứng viên).",
                }
            )

    # Nếu là pattern dài: tiền tố có bị cắt ở Pha 3 không?
    # Tiêu chí cắt tỉa thực sự: cận trên ÂM (SBOUND) khi ở chế độ âm,
    # còn STDAEUB kiểu PDF khi ở chế độ legacy.
    if len(pat) > 1:
        prefix = pat[:-1]
        pnode, _ = _pattern_entries(miner, prefix, f)
        sound_mode = getattr(miner, "sound", True)
        pbound = pnode.sbound if sound_mode else pnode.stdaeub
        plabel = "SBOUND(tiền tố" if sound_mode else "STDAEUB(tiền tố"
        if pbound < minae:
            reasons.append(
                {
                    "phase": "Pha 3",
                    "code": "PREFIX_BOUND_LT_MINAE",
                    "message": f"{plabel} {{{','.join(prefix)}}}) = "
                               f"{pbound:.4f} < minae → nhánh bị cắt tỉa, "
                               f"pattern này không được sinh ra.",
                }
            )
        else:
            reasons.append(
                {
                    "phase": "Pha 3",
                    "code": "PREFIX_BOUND_GE_MINAE",
                    "message": f"{plabel} {{{','.join(prefix)}}}) = "
                               f"{pbound:.4f} >= minae → nhánh vẫn mở, "
                               f"pattern được sinh bằng phép ghép.",
                }
            )
        # tiền tố có đạt HAEI không (điều kiện cần cho phép ghép)
        if pnode.sdae < minae:
            reasons.append(
                {
                    "phase": "Pha 3",
                    "code": "PREFIX_NOT_HAEI",
                    "message": f"Sdae(tiền tố) = {pnode.sdae:.4f} < minae → tiền tố "
                               f"không phải HAEI.",
                }
            )

    # Khả năng mở rộng: có item nào đứng sau trong thứ tự không
    order = list(miner.order)
    extensible = [it for it in order if it not in pat]
    sound_mode = getattr(miner, "sound", True)
    self_bound = node.sbound if sound_mode else node.stdaeub
    self_label = "SBOUND" if sound_mode else "STDAEUB"
    if self_bound < minae and is_haei:
        reasons.append(
            {
                "phase": "Pha 3",
                "code": "BOUND_LT_MINAE",
                "message": f"{self_label} = {self_bound:.4f} < minae → không thể mở rộng "
                           f"thêm (nhánh bị cắt), dù bản thân là HAEI."
                           + ("  [chế độ âm: cắt tỉa an toàn, không bỏ sót HAEI]"
                              if sound_mode else
                              "  [chế độ kiểu PDF: KHÔNG bảo đảm không bỏ sót]"),
            }
        )

    return {
        "pattern": list(pat),
        "size": len(pat),
        "inv": round(node.inv, 4),
        "ltid": miner.ltid,
        "f": f,
        "minae": minae,
        "is_haei": is_haei,
        "sdae": round(sdae, 6),
        "smdaeub": round(node.smdaeub, 6),
        "stdaeub": round(node.stdaeub, 6),
        "margin": round(sdae - minae, 6),
        "transactions_covered": len(rows),
        "entries": rows,
        "reasons": reasons,
        "extensible_items": extensible,
        "in_last_results": any(
            tuple(sorted(r["pattern"])) == pat for r in miner.results
        ),
    }


def explain_all(miner: HAEIMDampedMiner, f: float = 0.8, minae: float = 0.2) -> dict:
    """Giải thích toàn bộ kết quả lần khai thác gần nhất (kèm lý do)."""
    out = []
    for r in miner.results:
        out.append(explain_pattern(miner, r["pattern"], f=f, minae=minae))
    return {"count": len(out), "items": out}
