"""Core thuật toán HAEIM_Damped — bám sát PDF `TongHop_LuongXuLy_HAEIM_Damped.pdf`.

Ba pha (xem Sơ đồ tổng quan §5 trong PDF):
  Pha 1 Construction: mỗi khi có T_j mới — ghi u, inv, ae thô, MAEUB thô.
  Pha 2 Restructure:  định kỳ khai thác — áp f^(Ltid-tid), lọc SMDAEUB, sắp xếp,
                      tính Sdae / TDAEUB / STDAEUB.
  Pha 3 Expansion:    DFS đệ quy — Sdae>=minae -> kết quả,
                      STDAEUB>=minae -> ghép tiếp (dùng LTDAEUB dừng sớm).

Định nghĩa (khớp số liệu Ví dụ 1-4 trong PDF):
  u(X,Tj)   = sum_{i in X} qty(i,Tj) * eu(i)
  Inv(X)    = sum_{i in X} INV[i]            (Bảng 2, tĩnh, KHÔNG nhân qty;
              kiểm chứng: ae({a},T1)=4/96/1=0.0417)
  ae(X,Tj)  = u(X,Tj) / (Inv(X) * |X|)       (Công thức 5 — hiệu suất TRUNG BÌNH,
              chia cho |X|; với singleton |X|=1 nên ae=u/Inv)
  dae       = ae * f^(Ltid - tid)             (áp tại Restructure)
  Sdae(X)   = sum dae trên mọi Tj chứa X
  MAEUB(X,Tj) = max u(Y,Tj)/Inv(Y) trên các Y mở rộng X bằngDescending-utility
              greedy (HIỆU SUẤT, không chia len — chặn trên lỏng nhưng an toàn;
              nhờ đó SMDAEUB(a)=0.20+ > Sdae(a)=0.188, giữ {a} làm ứng viên;
              chỉ xét mục đứng SAU X trong thứ tự giảm dần tiện ích của Tj;
              VD MAEUB({a},T1)=0.0417 dù {a,c} có eff=0.0536 nhưng c đứng trước a)
  MDAEUB    = MAEUB * f^(Ltid-tid);  SMDAEUB = sum MDAEUB (lọc ở Restructure)
  TDAEUB    = cận trên chặt cho mọi phần mở rộng của X trong Tj:
                k=0  -> 0  (vd {c} đứng cuối => STDAEUB=0)
                k>0  -> (u + maxru) / ((Inv + minInv) * (|X|+1)) * w
              với maxru = tiện ích còn lại lớn nhất sau X trong Tj,
                  minInv = chi phí đầu tư nhỏ nhất còn lại sau X,
                  k = số mục còn lại sau X, w = f^(Ltid-tid).
              (PDF chỉ nêu "theo 3 trường hợp" mà ảnh công thức bị mất —
               cài đặt này giữ đúng semantics average-efficiency và tái hiện đúng
               hành vi cắt tỉa: STDAEUB(a)~0.17<0.2 cắt, STDAEUB(b)~0.28>=0.2 mở
               rộng, STDAEUB(c)=0. Xem README § Hiệu chỉnh.)
  STDAEUB(X)= sum TDAEUB (cắt tỉa ở Expansion)
  LTDAEUB   = cận trên cục bộ khi ghép P,Q: khởi tạo = STDAEUB(P),
              trừ dần đóng góp TDAEUB của giao dịch P có mà Q không có;
              nếu LTDAEUB < minae thì dừng sớm phép ghép (PDF § Pha 3 bước 3).
  Ghép đúng tiền tố: chỉ ghép 2 k-itemset cùng tiền tố k-1 mục đầu theo order;
  với singleton tiền tố rỗng nên mọi cặp đều hợp lệ (tái hiện Ví dụ 5 {b}x{c}).
  SMDAEUB của pattern sinh sau = Σ MDAEUB hiệu suất suy giảm (chặn trên đúng).

Lưu ý quan trọng trong PDF (§3): Construction chỉ lưu ae/MAEUB THÔ vì trọng số
f^(Ltid-tid) phụ thuộc Ltid thay đổi liên tục — suy giảm chỉ áp tại Restructure.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class DAEEntry:
    """Entry cấp giao dịch trong một node DAE-List."""

    tid: int
    u: float = 0.0            # tiện ích của pattern trong giao dịch
    ae: float = 0.0            # hiệu suất trung bình THÔ (chưa suy giảm)
    maeub: float = 0.0         # cận trên MAEUB THÔ (chưa suy giảm)
    pu: float = 0.0            # tiện ích tiền tố chung (khi ghép)
    # --- điền tại Restructure (sau khi biết Ltid, thứ tự sắp xếp) ---
    dae: float = 0.0           # ae * f^(Ltid-tid)
    mdaeub: float = 0.0        # maeub * f^(Ltid-tid)
    maxru: float = 0.0         # tiện ích còn lại lớn nhất sau pattern
    min_inv: float = 0.0       # chi phí đầu tư nhỏ nhất còn lại sau pattern
    k: int = 0                # số mục còn lại sau pattern
    tdaeub: float = 0.0        # cận trên chặt TDAEUB đã nhân suy giảm


@dataclass
class DAENode:
    """Node cấp cửa sổ — một pattern/tập mục."""

    pattern: Tuple[str, ...]
    inv: float = 0.0           # Inv(X) = sum INV[i]
    pi: float = 0.0            # PI: đầu tư của tiền tố chung (khi ghép)
    sdae: float = 0.0
    smdaeub: float = 0.0
    stdaeub: float = 0.0
    entries: List[DAEEntry] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "{" + ",".join(self.pattern) + "}"


class HAEIMDampedMiner:
    """Miner streaming HAEIM_Damped với đầy đủ 3 pha."""

    def __init__(self, eu: Dict[str, float], inv_table: Dict[str, float]):
        self.eu = dict(eu)
        self.inv_table = dict(inv_table)
        # transactions: tid -> {item: qty}
        self.transactions: Dict[int, Dict[str, float]] = {}
        # DAE-List toàn cục cho singleton (pha Construction tích lũy ở đây)
        self.nodes: Dict[Tuple[str, ...], DAENode] = {}
        # thứ tự toàn phần sau Restructure (tăng dần SMDAEUB) — dùng cho Expansion
        self.order: List[str] = []
        self.order_index: Dict[str, int] = {}
        # kết quả khai thác gần nhất
        self.results: List[Dict] = []
        self._lock = threading.RLock()

    def register_item(self, item: str, eu: float, inv: float) -> None:
        """Đăng ký item mới xuất hiện trên luồng (mở rộng ngoài a..f của PDF).

        PDF cố định 6 mục Bảng 2; luồng thực tế có thể phát sinh mục mới.
        """
        with self._lock:
            if eu <= 0 or inv <= 0:
                raise ValueError("eu/inv phải > 0")
            self.eu[item] = float(eu)
            self.inv_table[item] = float(inv)

    # ------------------------------------------------------------------ utils
    def utility_of(self, pattern: Tuple[str, ...], tid: int) -> float:
        t = self.transactions.get(tid, {})
        return sum(t.get(i, 0.0) * self.eu.get(i, 0.0) for i in pattern)

    def inv_of(self, pattern: Tuple[str, ...]) -> float:
        return sum(self.inv_table.get(i, 0.0) for i in pattern)

    def item_utility_in(self, item: str, tid: int) -> float:
        return self.transactions.get(tid, {}).get(item, 0.0) * self.eu.get(item, 0.0)

    @property
    def ltid(self) -> int:
        return max(self.transactions.keys()) if self.transactions else 0

    # ------------------------------------------------- PHA 1: CONSTRUCTION
    def construction(self, tid: int, items: List[Tuple[str, float]]) -> None:
        """Xử lý một giao dịch mới T_j: ghi u/ae/MAEUB thô cho từng singleton.

        Đúng PDF: chi phí O(|T_j|), không quét lại dữ liệu cũ; maxru/k để trống
        vì phụ thuộc thứ tự sau Restructure.
        """
        with self._lock:
            tmap: Dict[str, float] = {}
            for item, qty in items:
                if item not in self.eu or item not in self.inv_table:
                    raise KeyError(f"item '{item}' chưa đăng ký EU/INV")
                if float(qty) <= 0:
                    raise ValueError("qty phải > 0")
                tmap[item] = tmap.get(item, 0.0) + float(qty)
            if not tmap:
                raise ValueError("Transaction rỗng")
            self.transactions[tid] = tmap

            for item in tmap:
                key = (item,)
                node = self.nodes.get(key)
                if node is None:
                    node = DAENode(pattern=key, inv=self.inv_of(key))
                    self.nodes[key] = node
                u = self.item_utility_in(item, tid)
                ae = (u / (node.inv * len(key))) if node.inv else 0.0  # Công thức 5: u/(Inv*|X|)
                maeub = self._maeub_singleton_raw(item, tid, u, ae)
                node.entries.append(
                    DAEEntry(tid=tid, u=u, ae=ae, maeub=maeub, pu=0.0)
                )

    def _maeub_singleton_raw(self, item: str, tid: int, u: float, ae: float) -> float:
        """MAEUB thô cho singleton bằng greedy giảm dần tiện ích.

        Sắp xếp các mục trong Tj giảm dần theo utility; chỉ mở rộng X bằng các
        mục đứng SAU X (đúng semantics remaining-utility trong HUI/HAEIM).
        Giữ max hiệu suất u/Inv trên các bước mở rộng (chặn trên lỏng nhưng
        an toàn — không bỏ sót HAEI). Ví dụ PDF: {a} trong T1 (c:5,a:4,d:4,f:2)
        chỉ xét {a,d},{a,d,f} đều < 0.0417 nên MAEUB=0.0417.

        Điều kiện dừng an toàn: hiệu suất của phần mở rộng là trung bình có
        trọng số của hiệu suất hiện tại và các mục còn lại, nên không thể vượt
        max(hiệu suất hiện tại, max hiệu suất đơn của phần còn lại). Nếu cả hai
        đều <= best thì dừng sớm mà không đổi kết quả (đúng ý "điều kiện dừng"
        trong PDF Ví dụ 1).
        """
        tmap = self.transactions[tid]
        scored = sorted(
            ((self.item_utility_in(i, tid), i) for i in tmap),
            key=lambda x: (-x[0], x[1]),
        )
        pos = next((k for k, (_, it) in enumerate(scored) if it == item), None)
        if pos is None:
            return ae
        best = ae
        cur_u = u
        cur_inv = self.inv_table.get(item, 0.0)
        # hiệu suất đơn của từng mục phía sau — dùng cho điều kiện dừng
        suffix_single_eff = []
        for util, it in scored[pos + 1:]:
            inv = self.inv_table.get(it, 0.0)
            suffix_single_eff.append((util / inv) if inv > 0 else 0.0)
        # greedy: lần lượt thêm từng mục phía sau
        for idx, (_, nxt) in enumerate(scored[pos + 1:]):
            cur_u += self.item_utility_in(nxt, tid)
            cur_inv += self.inv_table.get(nxt, 0.0)
            if cur_inv <= 0:
                continue
            cand = cur_u / cur_inv
            if cand > best:
                best = cand
            # dừng sớm an toàn: không còn khả năng vượt best
            cur_eff = cur_u / cur_inv
            max_rem = max(suffix_single_eff[idx + 1:]) if idx + 1 < len(suffix_single_eff) else 0.0
            if max(cur_eff, max_rem) <= best:
                break
        return best

    # ------------------------------------------------- PHA 2: RESTRUCTURE
    def restructure(self, f: float, minae: float) -> List[DAENode]:
        """Áp suy giảm, lọc SMDAEUB, sắp xếp, tính Sdae/TDAEUB/STDAEUB.

        Trả về danh sách DAE-List ứng viên đã sắp xếp tăng dần SMDAEUB.
        """
        if not (0 < f < 1):
            raise ValueError("f phải thỏa 0<f<1 (PDF §1)")
        if minae < 0:
            raise ValueError("minae phải >= 0")
        with self._lock:
            ltid = self.ltid
            # 1. áp suy giảm + tổng
            for node in self.nodes.values():
                sdae = 0.0
                smdaeub = 0.0
                for e in node.entries:
                    w = (f ** (ltid - e.tid)) if ltid >= e.tid else 0.0
                    e.dae = e.ae * w
                    e.mdaeub = e.maeub * w
                    sdae += e.dae
                    smdaeub += e.mdaeub
                node.sdae = sdae
                node.smdaeub = smdaeub
            # 2. lọc sớm SMDAEUB < minae
            candidates = [n for n in self.nodes.values() if n.smdaeub >= minae and len(n.pattern) == 1]
            # 3. sắp xếp tăng dần SMDAEUB — thứ tự dùng cho Expansion
            candidates.sort(key=lambda n: (n.smdaeub, n.pattern))
            self.order = [n.pattern[0] for n in candidates]
            self.order_index = {it: k for k, it in enumerate(self.order)}
            # 4. duyệt ngược để tính maxru/minInv/k/TDAEUB (phụ thuộc thứ tự)
            for node in candidates:
                std = 0.0
                for e in node.entries:
                    self._fill_tight_fields(node, e, f, ltid)
                    std += e.tdaeub
                node.stdaeub = std
            return list(candidates)

    def _fill_tight_fields(self, node: DAENode, e: DAEEntry, f: float, ltid: int) -> None:
        """Tính maxru/minInv/k và TDAEUB cho một entry (sau khi có thứ tự).

        Với singleton: xét các mục sau item trong order.
        Với k-itemset (dùng khi tạo node join): xét các mục sau phần tử cuối
        của pattern trong order — đúng semantics "remaining" của PDF.
        """
        tmap = self.transactions.get(e.tid, {})
        if len(node.pattern) == 1:
            idx = self.order_index.get(node.pattern[0], -1)
        else:
            last = node.pattern[-1] if node.pattern else None
            idx = self.order_index.get(last, 999) if last else 999
            # pattern dài chứa item ngoài order (đã bị lọc) -> không còn remaining
            if idx >= 999:
                e.k = 0
                e.maxru = 0.0
                e.min_inv = 0.0
                e.tdaeub = self.tight_upper_bound(node, e, f, ltid)
                return
        # các mục còn lại phía sau trong thứ tự đã sắp xếp và có mặt trong Tj
        remaining = [it for it in self.order[idx + 1:] if it in tmap] if idx >= 0 else []
        e.k = len(remaining)
        if not remaining:
            e.maxru = 0.0
            e.min_inv = 0.0
        else:
            utils = [self.item_utility_in(it, e.tid) for it in remaining]
            invs = [self.inv_table.get(it, 0.0) for it in remaining]
            e.maxru = max(utils) if utils else 0.0
            e.min_inv = min(invs) if invs else 0.0
        e.tdaeub = self.tight_upper_bound(node, e, f, ltid)

    @staticmethod
    def tight_upper_bound(node: DAENode, e: DAEEntry, f: float, ltid: int) -> float:
        """TDAEUB theo 3 trường hợp (semantics PDF § Pha 2 bước 4).

        - TH1 (k == 0): không còn mục nào sau pattern -> 0.
        - TH2 (không có thông tin còn lại): dùng dae.
        - TH3 (còn lại): (u + maxru) / ((Inv + minInv) * (|X|+1)) * w.
          Đây là ae của phần mở rộng 1-mục tốt nhất — chặn trên mọi extension
          dài hơn vì |Y|>=|X|+1. VD order a<b<c: STDAEUB(a)~0.17<0.2 (cắt),
          STDAEUB(b)~0.28>=0.2 (mở rộng {b}x{c}), STDAEUB(c)=0.
        """
        w = (f ** (ltid - e.tid)) if ltid >= e.tid else 0.0
        if e.k == 0:
            return 0.0
        if e.maxru <= 0 or e.min_inv <= 0 or node.inv <= 0:
            return e.dae
        plen = len(node.pattern) if node.pattern else 1
        return (e.u + e.maxru) / ((node.inv + e.min_inv) * (plen + 1)) * w

    # ------------------------------------------------- PHA 3: EXPANSION
    def expansion(self, candidates: List[DAENode], f: float, minae: float) -> List[Dict]:
        """DFS đệ quy sinh pattern dài hơn từ các DAE-List đã lọc & sắp xếp.

        Đúng PDF § Pha 3:
          1. Sdae(P) >= minae -> thêm vào DHAEIs.
          2. STDAEUB(P) < minae -> cắt cả nhánh.
          3. Ngược lại ghép P với các DAE-List đứng sau (cùng tiền tố),
             dùng LTDAEUB bên trong _join để dừng sớm phép ghép vô vọng.
        """
        if minae < 0:
            raise ValueError("minae phải >= 0")
        with self._lock:
            results: List[Dict] = []
            ltid = self.ltid

            def emit(node: DAENode) -> None:
                if node.sdae >= minae:
                    results.append(
                        {"pattern": list(node.pattern), "sdae": round(node.sdae, 4),
                         "smdaeub": round(node.smdaeub, 4), "stdaeub": round(node.stdaeub, 4)}
                    )

            def dfs(node: DAENode, cond: List[DAENode]) -> None:
                emit(node)
                if node.stdaeub < minae:
                    return
                for j, other in enumerate(cond):
                    joined = self._join(node, other, f, ltid, minae)
                    if joined is None:
                        continue
                    dfs(joined, cond[j + 1:])

            # root: mỗi singleton làm gốc, cond = các singleton đứng sau nó
            for i, node in enumerate(candidates):
                dfs(node, candidates[i + 1:])
            # khử trùng lặp (giữ Sdae lớn nhất)
            uniq: Dict[Tuple[str, ...], Dict] = {}
            for r in results:
                k = tuple(sorted(r["pattern"]))
                if k not in uniq or r["sdae"] > uniq[k]["sdae"]:
                    uniq[k] = r
            self.results = sorted(uniq.values(), key=lambda r: (len(r["pattern"]), r["pattern"]))
            return self.results

    def _join(self, px: DAENode, py: DAENode, f: float, ltid: int, minae: float) -> DAENode | None:
        """Ghép 2 DAE-List cùng tiền tố tạo pattern mới Pxy (2 con trỏ trên tidList).

        Đúng PDF § Pha 3 bước 3:
        - Chỉ ghép khi cùng tiền tố dài n-1 (với singleton n=1 tiền tố rỗng
          nên mọi cặp đều hợp lệ; với k>=2 phải chia sẻ k-1 mục đầu theo order).
        - entry mới khi trùng tid: u = u_x + u_y - PU(prefix), PU=0 nếu rỗng;
          Inv(Pxy) = Inv(Px) + Inv(Py) - PI(prefix).
        - LTDAEUB: khởi tạo = STDAEUB(Px), trừ dần TDAEUB của các tid Px có mà
          Py không có; nếu LTDAEUB < minae thì dừng sớm, trả None.
        - Sdae = Σ dae (ae suy giảm); SMDAEUB = Σ MDAEUB (hiệu suất suy giảm,
          chặn trên đúng — KHÔNG gán bằng Sdae); STDAEUB = Σ TDAEUB.
        """
        if len(px.pattern) != len(py.pattern):
            return None
        # kiểm tra cùng tiền tố (theo thứ tự order): px[:-1] == py[:-1]
        if len(px.pattern) > 1 and tuple(px.pattern[:-1]) != tuple(py.pattern[:-1]):
            return None
        # pattern mới: giữ thứ tự order để remaining/TDAEUB nhất quán
        new_items = sorted(set(px.pattern) | set(py.pattern),
                           key=lambda it: (self.order_index.get(it, 999), it))
        # ghép cùng độ dài mà không sinh mục mới (trùng nhau) -> bỏ
        if len(new_items) != len(px.pattern) + 1:
            return None
        new_pattern = tuple(new_items)
        # tiền tố chung = giao (với singleton thì rỗng)
        prefix = tuple(sorted(set(px.pattern) & set(py.pattern)))
        pi = self.inv_of(prefix) if prefix else 0.0
        new_inv = px.inv + py.inv - pi
        if new_inv <= 0:
            return None
        # index entries để join 2 con trỏ trên tidList đã sắp xếp
        x_by_tid = {e.tid: e for e in px.entries}
        y_by_tid = {e.tid: e for e in py.entries}
        x_tids = sorted(x_by_tid)
        y_set = set(y_by_tid)
        common = sorted(set(x_by_tid) & y_set)
        if not common:
            return None
        # LTDAEUB dừng sớm (PDF): STDAEUB(Px) trừ đóng góp tid lệch
        ltdaeub = px.stdaeub
        for tid in x_tids:
            if tid not in y_set:
                ltdaeub -= x_by_tid[tid].tdaeub
                if ltdaeub < minae:
                    return None
        if ltdaeub < minae:
            return None
        pu_map: Dict[int, float] = {}
        if prefix:
            for tid in common:
                pu_map[tid] = self.utility_of(prefix, tid)
        node = DAENode(pattern=new_pattern, inv=new_inv, pi=pi)
        sdae = 0.0
        smdaeub = 0.0
        for tid in common:
            ex, ey = x_by_tid[tid], y_by_tid[tid]
            pu = pu_map.get(tid, 0.0)
            u = ex.u + ey.u - pu
            plen = len(new_pattern)
            ae = u / (new_inv * plen) if new_inv and plen else 0.0
            eff = u / new_inv if new_inv else 0.0
            w = (f ** (ltid - tid)) if ltid >= tid else 0.0
            dae = ae * w
            mdaeub = eff * w
            sdae += dae
            smdaeub += mdaeub
            e = DAEEntry(tid=tid, u=u, ae=ae, maeub=eff,
                         pu=pu, dae=dae, mdaeub=mdaeub)
            node.entries.append(e)
        node.sdae = sdae
        node.smdaeub = smdaeub
        # tính maxru/minInv/k/TDAEUB cho node mới theo thứ tự hiện tại
        std = 0.0
        for e in node.entries:
            self._fill_tight_fields(node, e, f, ltid)
            # _fill đã tính tdaeub; đồng bộ mdaeub giữ nguyên eff suy giảm
            std += e.tdaeub
        node.stdaeub = std
        return node

    # ------------------------------------------------- tiện ích tổng hợp
    def mine(self, f: float, minae: float) -> Dict:
        """Chạy trọn Restructure + Expansion (giữ Construction đã tích lũy)."""
        with self._lock:
            if not self.transactions:
                raise ValueError("Luồng rỗng")
            # gọi nội bộ tránh deadlock (RLock cho phép restructure/expansion lồng nhau)
            cands = self.restructure(f, minae)
            dhaeis = self.expansion(cands, f, minae)
            return {
                "f": f, "ltid": self.ltid, "minae": minae,
                "order": list(self.order),
                "candidates": [
                    {"pattern": list(n.pattern), "sdae": round(n.sdae, 4),
                     "smdaeub": round(n.smdaeub, 4), "stdaeub": round(n.stdaeub, 4)}
                    for n in cands
                ],
                "dhaeis": dhaeis,
            }

    def reset(self) -> None:
        with self._lock:
            self.transactions.clear()
            self.nodes.clear()
            self.order = []
            self.order_index = {}
            self.results = []

    def load_example_stream(self) -> None:
        from .data import EXAMPLE_STREAM
        with self._lock:
            # reset nội bộ (không gọi self.reset để tránh lồng lock không cần thiết
            # — RLock vẫn an toàn, nhưng tách rõ để dễ đọc)
            self.transactions.clear()
            self.nodes.clear()
            self.order = []
            self.order_index = {}
            self.results = []
            for tid in sorted(EXAMPLE_STREAM):
                # construction cũng dùng lock (RLock nên an toàn khi lồng)
                self.construction(tid, [(i, q) for i, q in EXAMPLE_STREAM[tid]])
