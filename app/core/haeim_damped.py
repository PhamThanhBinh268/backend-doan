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
  SBOUND    = cận trên AN TOÀN của Sdae của mọi phần mở rộng Y ⊋ X:
                 SBOUND(X) = sum_{Tj chứa X} B(X,Tj) * f^(Ltid-tid)
              với B(X,Tj) = max_{m=1..|R|} (u(X)+U_max(m)) / ((Inv(X)+I_min(m))·(|X|+m))
                 R = các mục còn lại trong Tj,
                 U_max(m) = tổng tiện ích lớn nhất của m mục trong R,
                 I_min(m) = tổng chi phí đầu tư nhỏ nhất của m mục trong R.
              Cơ sở: với mọi Z ⊆ R, |Z|=m:
                 u(X∪Z) <= u(X)+U_max(m)  và  Inv(X∪Z) >= Inv(X)+I_min(m)
                 => eff(X∪Z) <= bound_m  =>  ae(X∪Z) = eff/(|X|+m) <= bound_m/(|X|+m)
              => SBOUND(X) >= Sdae(Y) cho mọi Y ⊋ X
              => nếu SBOUND(X) < minae thì KHÔNG phần mở rộng nào của X là HAEI
              (xem `app/core/bounds.py` — chứng minh đầy đủ + bản cận chặt hơn
               khi giỏ hàng nhỏ: duyệt tập mục con chính xác).
  TDAEUB    = cận trên kiểu PDF cho phần mở rộng THÊM 1 MỤC:
                k=0  -> 0  (vd {c} đứng cuối => STDAEUB=0)
                k>0  -> (u + maxru) / ((Inv + minInv) * (|X|+1)) * w
              với maxru = tiện ích còn lại lớn nhất sau X trong Tj,
                  minInv = chi phí đầu tư nhỏ nhất còn lại sau X,
                  k = số mục còn lại sau X, w = f^(Ltid-tid).
              (PDF chỉ nêu "theo 3 trường hợp" mà ảnh công thức bị mất —
               cài đặt này giữ đúng semantics average-efficiency và tái hiện đúng
               hành vi cắt tỉa: STDAEUB(a)~0.17<0.2 cắt, STDAEUB(b)~0.28>=0.2 mở
               rộng, STDAEUB(c)=0. Xem README § Hiệu chỉnh.)
  STDAEUB(X)= sum TDAEUB (chỉ để HIỂN THỊ — không dùng cắt tỉa, xem SBOUND)
  LTDAEUB   = cận trên cục bộ khi ghép P,Q: khởi tạo = SBOUND(P) (bản âm) hoặc
              STDAEUB(P) (bản kiểu PDF), trừ dần đóng góp của giao dịch P có mà
              Q không có; nếu LTDAEUB < minae thì dừng sớm phép ghép
              (PDF § Pha 3 bước 3).
  Ghép đúng tiền tố: chỉ ghép 2 k-itemset cùng tiền tố k-1 mục đầu theo order;
  với singleton tiền tố rỗng nên mọi cặp đều hợp lệ (tái hiện Ví dụ 5 {b}x{c}).
  SMDAEUB của pattern sinh sau = Σ MDAEUB hiệu suất suy giảm (chặn trên đúng).

CẮT TỈA AN TOÀN (đóng góp chính của đồ án — xem `app/core/bounds.py`)
------------------------------------------------------------------
Công thức TDAEUB kiểu PDF ở trên chỉ chặn trên **đúng** với phần mở rộng thêm
**1 mục**; với phần mở rộng thêm >= 2 mục, tổng tiện ích có thể vượt
`u(X)+maxru` ⇒ cận trên **bị vi phạm** ⇒ Pha 3 cắt nhánh chứa HAEI thật ⇒
**bỏ sót kết quả** (đo được: luồng 1000 GD / 18 mục thiếu `{f,m}`, khớp 97,96%).

Vì vậy mọi phép cắt tỉa ở chế độ mặc định (`sound=True`) dùng **cận trên ÂM**
(SBOUND ở trên) ⇒ **không bao giờ bỏ sót HAEI** (khớp 100% ground truth,
`app/core/baseline.py`). Chế độ `sound=False` giữ hành vi kiểu PDF (nhanh hơn,
không âm) để đối chiếu thực nghiệm.

Lưu ý quan trọng trong PDF (§3): Construction chỉ lưu ae/MAEUB THÔ vì trọng số
f^(Ltid-tid) phụ thuộc Ltid thay đổi liên tục — suy giảm chỉ áp tại Restructure.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field

from .data import CU, EU, EXAMPLE_STREAM, INV
from .bounds import TxIndex, build_index, sound_bound

__all__ = ["DAEEntry", "DAENode", "HAEIMDampedMiner"]

_ROUND_DIGITS = 4


def _round4(x: float) -> float:
    return round(float(x), _ROUND_DIGITS)


def _validate_decay(f: float) -> float:
    f = float(f)
    if not 0.0 < f < 1.0:
        raise ValueError("f phải thỏa 0<f<1 (PDF §1)")
    return f


def _validate_minae(minae: float) -> float:
    minae = float(minae)
    if minae < 0:
        raise ValueError("minae phải >= 0")
    return minae


@dataclass(slots=True)
class DAEEntry:
    """Entry cấp giao dịch trong một node DAE-List."""

    tid: int
    u: float = 0.0            # tiện ích của pattern trong giao dịch
    ae: float = 0.0           # hiệu suất trung bình THÔ (chưa suy giảm)
    maeub: float = 0.0        # cận trên MAEUB THÔ (chưa suy giảm)
    pu: float = 0.0           # tiện ích tiền tố chung (khi ghép)
    # --- điền tại Restructure (sau khi biết Ltid, thứ tự sắp xếp) ---
    dae: float = 0.0          # ae * f^(Ltid-tid)
    mdaeub: float = 0.0       # maeub * f^(Ltid-tid)
    maxru: float = 0.0        # tiện ích còn lại lớn nhất sau pattern
    min_inv: float = 0.0      # chi phí đầu tư nhỏ nhất còn lại sau pattern
    k: int = 0                # số mục còn lại sau pattern
    tdaeub: float = 0.0       # cận trên chặt TDAEUB đã nhân suy giảm (theo PDF)
    # --- cận trên ÂM (sound) dùng cho quyết định cắt tỉa ---
    sbnd: float = 0.0         # max ae của MỌI phần mở rộng trong giao dịch này
                              # (đã nhân suy giảm) — luôn >= giá trị thật


@dataclass(slots=True)
class DAENode:
    """Node cấp cửa sổ — một pattern/tập mục."""

    pattern: tuple[str, ...]
    inv: float = 0.0          # Inv(X) = sum INV[i]
    pi: float = 0.0           # PI: đầu tư của tiền tố chung (khi ghép)
    sdae: float = 0.0
    smdaeub: float = 0.0
    stdaeub: float = 0.0
    #: Σ sbnd·w — cận trên ÂM cho Sdae của mọi phần mở rộng của pattern.
    #: Dùng để cắt tỉa: nếu < minae thì chắc chắn không có phần mở rộng nào
    #: là HAEI (an toàn tuyệt đối).
    sbound: float = 0.0
    entries: list[DAEEntry] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "{" + ",".join(self.pattern) + "}"


class HAEIMDampedMiner:
    """Miner streaming HAEIM_Damped với đầy đủ 3 pha."""

    def __init__(self, eu: dict[str, float], inv_table: dict[str, float],
                 cu: dict[str, float] | None = None, sound: bool = True):
        self.eu = dict(eu)
        self.inv_table = dict(inv_table)
        self.cu: dict[str, float] = dict(cu) if cu else {}
        # `sound=True` (mặc định): mọi phép cắt tỉa dùng CẬN TRÊN ÂM → không
        #   bao giờ bỏ sót HAEI (khớp 100% ground truth).
        # `sound=False`: dùng cận trên "chặt" của bản đầu (theo 1 phần mở rộng)
        #   → nhanh hơn nhưng KHÔNG an toàn ở quy mô lớn (dùng để so sánh).
        self.sound = bool(sound)
        # transactions: tid -> {item: qty}
        self.transactions: dict[int, dict[str, float]] = {}
        # DAE-List toàn cục cho singleton (pha Construction tích lũy ở đây)
        self.nodes: dict[tuple[str, ...], DAENode] = {}
        # pattern dài sinh ra trong Expansion gần nhất (để /api/dae-lists soi được)
        self.extra_nodes: dict[tuple[str, ...], DAENode] = {}
        # thứ tự toàn phần sau Restructure (tăng dần SMDAEUB) — dùng cho Expansion
        self.order: list[str] = []
        self.order_index: dict[str, int] = {}
        # kết quả khai thác gần nhất
        self.results: list[dict] = []
        self._lock = threading.RLock()
        # chỉ mục phụ trợ theo giao dịch (dựng ở Restructure) — phục vụ cận trên âm
        self._tx_index: dict[int, TxIndex] = {}
        # hệ số suy giảm của lần Restructure gần nhất (dùng khi hiển thị DAE-List)
        self._last_f: float = 0.8
        # nhãn "DAE-List đã được Restructure cho (version, f, minae)" — dùng để
        # biết order/order_index còn mới hay không (vd /api/explain gọi trước mine)
        self._restructure_key: tuple | None = None
        self._restructure_version: int = -1
        # --- tối ưu: version + cache mine ---
        # _version tăng mỗi khi luồng đổi (construction/register/reset/load),
        # dùng làm 1 phần cache-key để mine lặp lại không chạy lại vô ích.
        self._version: int = 0
        self._mine_cache: dict | None = None
        self._mine_cache_key: tuple | None = None
        self.last_stats: dict = {}

    @property
    def version(self) -> int:
        return self._version

    def register_item(self, item: str, eu: float, inv: float,
                      cu: float | None = None) -> None:
        """Đăng ký item mới xuất hiện trên luồng (mở rộng ngoài a..f của PDF).

        PDF cố định 6 mục Bảng 2; luồng thực tế có thể phát sinh mục mới.
        Từ chối ghi đè item đã tồn tại để tránh entries cũ (ae/maeub) và
        node.inv bị stale theo eu/inv mới.
        """
        item = str(item).strip()
        if not item:
            raise ValueError("item rỗng")
        if float(eu) <= 0 or float(inv) <= 0:
            raise ValueError("eu/inv phải > 0")
        if cu is not None and float(cu) <= 0:
            raise ValueError("cu phải > 0")
        with self._lock:
            if item in self.eu or item in self.inv_table:
                raise ValueError(f"item '{item}' đã tồn tại")
            self.eu[item] = float(eu)
            self.inv_table[item] = float(inv)
            if cu is not None:
                self.cu[item] = float(cu)
            self.extra_nodes.clear()
            self._version += 1
            self._mine_cache = None
            self._mine_cache_key = None

    # ------------------------------------------------------------------ utils
    def utility_of(self, pattern: tuple[str, ...], tid: int) -> float:
        t = self.transactions.get(tid, {})
        return sum(t.get(i, 0.0) * self.eu.get(i, 0.0) for i in pattern)

    def inv_of(self, pattern: tuple[str, ...]) -> float:
        return sum(self.inv_table.get(i, 0.0) for i in pattern)

    def item_utility_in(self, item: str, tid: int) -> float:
        return self.transactions.get(tid, {}).get(item, 0.0) * self.eu.get(item, 0.0)

    @property
    def ltid(self) -> int:
        return max(self.transactions.keys()) if self.transactions else 0

    def _decay_weights(self, f: float, ltid: int) -> dict[int, float]:
        """Tiền tính bảng trọng số suy giảm w(tid) = f^(ltid-tid) — tối ưu.

        Thay vì gọi `f ** (ltid-tid)` cho mỗi entry (mỗi node lặp lại phép `**`
        đắt tiền), tính 1 lần cho mỗi tid rồi tra cứu O(1). Kết quả số học
        giống hệt, chỉ giảm số phép lũy thừa từ O(Σ entries) xuống O(#tids).
        """
        return {tid: (f ** (ltid - tid)) for tid in self.transactions}

    @staticmethod
    def _resolve_weight(
        e: DAEEntry, f: float, ltid: int,
        weights: dict[int, float] | None = None,
        w: float | None = None,
    ) -> float:
        if w is not None:
            return w
        if weights is not None:
            return weights.get(e.tid, 0.0)
        return (f ** (ltid - e.tid)) if ltid >= e.tid else 0.0

    def _clear_locked(self) -> None:
        """Xóa toàn bộ trạng thái luồng (gọi khi đã giữ lock)."""
        self.transactions.clear()
        self.nodes.clear()
        self.extra_nodes.clear()
        self.order = []
        self.order_index = {}
        self.results = []
        self._mine_cache = None
        self._mine_cache_key = None
        self.last_stats = {}

    # ------------------------------------------------- PHA 1: CONSTRUCTION
    def _construct_locked(self, tid: int, items: list[tuple[str, float]]) -> None:
        """Ghi một giao dịch khi đã giữ lock (không đụng version/cache).

        Tách riêng để `construction` (lẻ) và `bulk_construction` (lô) dùng chung
        một đường code duy nhất — tránh lệch logic.
        """
        if not isinstance(tid, int) or tid <= 0:
            raise ValueError(f"tid phải là số nguyên > 0, nhận {tid!r}")
        tmap: dict[str, float] = {}
        for item, qty in items:
            if item not in self.eu or item not in self.inv_table:
                raise KeyError(f"item '{item}' chưa đăng ký EU/INV")
            if float(qty) <= 0:
                raise ValueError("qty phải > 0")
            tmap[item] = tmap.get(item, 0.0) + float(qty)
        if not tmap:
            raise ValueError("Transaction rỗng")
        if tid in self.transactions:
            raise ValueError(f"tid {tid} đã tồn tại")
        self.transactions[tid] = tmap

        # tiền tính 1 lần: utility từng item + thứ tự giảm dần tiện ích
        util_map = {it: q * self.eu[it] for it, q in tmap.items()}
        scored = sorted(
            ((util_map[it], it) for it in tmap),
            key=lambda x: (-x[0], x[1]),
        )
        pos_of = {it: k for k, (_, it) in enumerate(scored)}
        # Hậu tố "max hiệu suất đơn" — tính ĐÚNG 1 LẦN cho cả giao dịch thay vì
        # dựng lại cho từng mục (tiết kiệm ~4x thời gian Pha 1, kết quả y hệt).
        # gsuffix[j] = max hiệu suất của scored[j:]
        eff_sorted: list[float] = []
        for _, it in scored:
            iv = self.inv_table.get(it, 0.0)
            eff_sorted.append((util_map[it] / iv) if iv > 0 else 0.0)
        gsuffix = [0.0] * (len(eff_sorted) + 1)
        for k in range(len(eff_sorted) - 1, -1, -1):
            gsuffix[k] = eff_sorted[k] if eff_sorted[k] > gsuffix[k + 1] else gsuffix[k + 1]

        for item in tmap:
            key = (item,)
            node = self.nodes.get(key)
            if node is None:
                node = DAENode(pattern=key, inv=self.inv_of(key))
                self.nodes[key] = node
            u = util_map[item]
            ae = (u / (node.inv * len(key))) if node.inv else 0.0  # Công thức 5: u/(Inv*|X|)
            maeub = self._maeub_singleton_raw(
                item, tid, u, ae, scored=scored, pos_of=pos_of, util_map=util_map,
                gsuffix=gsuffix,
            )
            node.entries.append(
                DAEEntry(tid=tid, u=u, ae=ae, maeub=maeub, pu=0.0)
            )

    def construction(self, tid: int, items: list[tuple[str, float]]) -> None:
        """Xử lý một giao dịch mới T_j: ghi u/ae/MAEUB thô cho từng singleton.

        Đúng PDF: chi phí O(|T_j|), không quét lại dữ liệu cũ; maxru/k để trống
        vì phụ thuộc thứ tự sau Restructure.

        Tối ưu: sắp xếp Tj giảm dần tiện ích 1 lần duy nhất rồi tái dùng cho
        mọi item khi tính MAEUB (thay vì sort lại cho mỗi item).
        Kết quả số học giống hệt bản sort-lặp.
        """
        with self._lock:
            self._construct_locked(tid, items)
            self.extra_nodes.clear()
            self._version += 1
            self._mine_cache = None
            self._mine_cache_key = None

    def _maeub_singleton_raw(
        self,
        item: str,
        tid: int,
        u: float,
        ae: float,
        scored: list[tuple[float, str]] | None = None,
        pos_of: dict[str, int] | None = None,
        util_map: dict[str, float] | None = None,
        gsuffix: list[float] | None = None,
    ) -> float:
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

        `gsuffix[j]` = max hiệu suất đơn của các mục đứng từ vị trí j trở đi
        trong `scored` — truyền vào từ `_construct_locked` (dựng 1 lần/giao
        dịch) để không phải tính lại cho từng mục.
        """
        if scored is None or util_map is None:
            # fallback tương thích: tự tính khi gọi lẻ (không qua construction)
            tmap = self.transactions.get(tid, {})
            util_map = {it: self.item_utility_in(it, tid) for it in tmap}
            scored = sorted(
                ((util_map[it], it) for it in tmap),
                key=lambda x: (-x[0], x[1]),
            )
            pos_of = {it: k for k, (_, it) in enumerate(scored)}
        pos = pos_of.get(item) if pos_of is not None else None
        if pos is None:
            return ae
        best = ae
        cur_u = u
        cur_inv = self.inv_table.get(item, 0.0)
        n = len(scored)
        if gsuffix is None:
            # tự dựng hậu tố (đường dự phòng khi gọi trực tiếp)
            gsuffix = [0.0] * (n + 1)
            for k in range(n - 1, -1, -1):
                iv = self.inv_table.get(scored[k][1], 0.0)
                eff = (util_map[scored[k][1]] / iv) if iv > 0 else 0.0
                gsuffix[k] = eff if eff > gsuffix[k + 1] else gsuffix[k + 1]
        # greedy: lần lượt thêm từng mục phía sau (dùng util_map có sẵn)
        for j in range(pos + 1, n):
            nxt = scored[j][1]
            cur_u += util_map.get(nxt, 0.0)
            cur_inv += self.inv_table.get(nxt, 0.0)
            if cur_inv <= 0:
                continue
            cand = cur_u / cur_inv
            if cand > best:
                best = cand
            # dừng sớm an toàn: không còn khả năng vượt best
            max_rem = gsuffix[j + 1]
            if max(cand, max_rem) <= best:
                break
        return best

    # ------------------------------------------------- PHA 2: RESTRUCTURE
    def restructure(
        self,
        f: float,
        minae: float,
        weights: dict[int, float] | None = None,
    ) -> list[DAENode]:
        """Áp suy giảm, lọc SMDAEUB, sắp xếp, tính Sdae/TDAEUB/STDAEUB.

        Trả về danh sách DAE-List ứng viên đã sắp xếp tăng dần SMDAEUB.

        `weights` (tuỳ chọn): bảng trọng số suy giảm f^(Ltid-tid) đã tiền tính —
        truyền vào để Restructure và Expansion dùng chung (tiết kiệm 1 lần
        tính lũy thừa cho mỗi mine).
        """
        f = _validate_decay(f)
        minae = _validate_minae(minae)
        with self._lock:
            self.extra_nodes.clear()
            self._last_f = f          # nhớ f hiện tại để tính cận "PDF" khi hiển thị
            ltid = self.ltid
            # Tối ưu: tiền tính bảng trọng số 1 lần (thay vì ** cho mỗi entry).
            if weights is None:
                weights = self._decay_weights(f, ltid)
            # Chỉ mục phụ trợ cho cận trên ÂM (dựng 1 lần/mine, không tính lại
            # cho từng entry). Chỉ mục KHÔNG phụ thuộc thứ tự nên dựng trước.
            self._tx_index = {
                tid: build_index(tid, tmap, self.eu, self.inv_table)
                for tid, tmap in self.transactions.items()
            }
            # 1. áp suy giảm + tổng (entries sắp xếp theo tid để _join two-pointer)
            for node in self.nodes.values():
                sdae = 0.0
                smdaeub = 0.0
                node.entries.sort(key=lambda x: x.tid)
                for e in node.entries:
                    w = weights.get(e.tid, 0.0)
                    e.dae = e.ae * w
                    e.mdaeub = e.maeub * w
                    sdae += e.dae
                    smdaeub += e.mdaeub
                node.sdae = sdae
                node.smdaeub = smdaeub
                # cận trên âm (dùng cho quyết định cắt tỉa — xem bounds.py)
                if self.sound:
                    self._apply_sound_bounds(node, weights, minae)
                else:
                    node.sbound = 0.0
            # 2. lọc ỨNG VIÊN — điều kiện AN TOÀN:
            #    giữ node nếu (a) node có thể là HAEI (smdaeub >= minae, do
            #    smdaeub >= sdae) HOẶC (b) node còn có thể sinh ra phần mở rộng
            #    là HAEI (sbound >= minae — cận trên âm).
            #    Bỏ sót nhánh là mất HAEI → điều kiện (b) là bắt buộc.
            if self.sound:
                candidates = [
                    n for n in self.nodes.values()
                    if n.smdaeub >= minae or n.sbound >= minae
                ]
            else:
                # bản cũ: chỉ dựa vào SMDAEUB (chặt nhưng KHÔNG âm)
                candidates = [n for n in self.nodes.values() if n.smdaeub >= minae]
            # 3. sắp xếp tăng dần SMDAEUB — thứ tự dùng cho Expansion
            candidates.sort(key=lambda n: (n.smdaeub, n.pattern))
            self.order = [n.pattern[0] for n in candidates]
            self.order_index = {it: k for k, it in enumerate(self.order)}
            # 4. duyệt ngược để tính maxru/minInv/k/TDAEUB (phụ thuộc thứ tự)
            for node in candidates:
                std = 0.0
                for e in node.entries:
                    self._fill_tight_fields(node, e, f, ltid, weights=weights)
                    std += e.tdaeub
                node.stdaeub = std
            # đánh dấu DAE-List còn mới (dùng bởi ensure_restructured) — phải
            # gồm chế độ cắt tỉa vì kết quả Restructure phụ thuộc nó
            self._restructure_key = (round(float(f), 6), round(float(minae), 6),
                                     self.sound)
            self._restructure_version = self._version
            return list(candidates)

    def ensure_restructured(self, f: float, minae: float) -> None:
        """Đảm bảo DAE-List (order/order_index/Sdae/STDAEUB) khớp luồng + tham số.

        Dùng cho các API chỉ đọc (vd `/api/explain`) để không phải chạy `mine()`
        nhưng vẫn có số liệu đúng. Chỉ Restructure lại khi thực sự cần
        (luồng đổi hoặc đổi f/minae) — nếu không thì bỏ qua, giữ `extra_nodes`.
        """
        f = _validate_decay(f)
        minae = _validate_minae(minae)
        key = (round(float(f), 6), round(float(minae), 6), self.sound)
        with self._lock:
            if self._restructure_version == self._version and self._restructure_key == key:
                return
            self.restructure(f, minae)

    def _apply_sound_bounds(self, node: DAENode, weights: dict[int, float],
                            minae: float | None = None) -> float:
        """Tính cận trên ÂM cho node: e.sbnd và node.sbound (Σ sbnd·w).

        `sbnd` = max_{Z ⊆ R} ae(X∪Z, Tj) — cận trên của hiệu suất trung bình
        của **mọi** phần mở rộng của X trong giao dịch Tj (đã nhân suy giảm).
        Xem `app/core/bounds.py` cho chứng minh tính đúng.

        `minae` (tuỳ chọn) chỉ là gợi ý để bỏ qua việc tính cận chính xác khi
        cận lỏng đã chắc chắn dưới ngưỡng (quyết định cắt tỉa không đổi).
        """
        total = 0.0
        for e in node.entries:
            idx = self._tx_index.get(e.tid)
            w = weights.get(e.tid, 0.0)
            e.sbnd = (
                sound_bound(idx, node.pattern, e.u, node.inv, minae_hint=minae) * w
                if idx is not None else 0.0
            )
            total += e.sbnd
        node.sbound = total
        return total

    def _fill_tight_fields(
        self,
        node: DAENode,
        e: DAEEntry,
        f: float,
        ltid: int,
        weights: dict[int, float] | None = None,
        tx_sets: dict[int, set] | None = None,
    ) -> None:
        """Tính maxru/minInv/k và TDAEUB cho một entry (sau khi có thứ tự).

        Với singleton: xét các mục sau item trong order.
        Với k-itemset (dùng khi tạo node join): xét các mục sau phần tử cuối
        của pattern trong order — đúng semantics "remaining" của PDF.

        Tối ưu: duyệt **các mục có trong Tj** và hỏi "vị trí trong order có
        lớn hơn idx không" (O(|T_j|)) thay vì quét cả `order` rồi lọc
        (O(|order|)). Với luồng nhiều mục nhưng giỏ hàng nhỏ thì nhanh hơn nhiều.
        """
        tmap = self.transactions.get(e.tid, {})
        if len(node.pattern) == 1:
            idx: int | None = self.order_index.get(node.pattern[0])
        else:
            last = node.pattern[-1] if node.pattern else None
            idx = self.order_index.get(last) if last else None
            # pattern dài chứa item ngoài order (đã bị lọc) -> không còn remaining
            if idx is None:
                e.k = 0
                e.maxru = 0.0
                e.min_inv = 0.0
                e.tdaeub = self.tight_upper_bound(node, e, f, ltid, weights=weights)
                return
        if idx is None:
            remaining: list[str] = []
        else:
            # các mục còn lại phía sau trong thứ tự đã sắp xếp và có mặt trong Tj
            oidx = self.order_index
            remaining = [it for it in tmap if oidx.get(it, -1) > idx]
        e.k = len(remaining)
        if not remaining:
            e.maxru = 0.0
            e.min_inv = 0.0
        else:
            # tra utility trực tiếp từ tmap (tránh gọi hàm cho mỗi item)
            eu = self.eu
            invt = self.inv_table
            best_u = 0.0
            best_inv: float | None = None
            for it in remaining:
                uu = tmap.get(it, 0.0) * eu.get(it, 0.0)
                if uu > best_u:
                    best_u = uu
                iv = invt.get(it, 0.0)
                if best_inv is None or iv < best_inv:
                    best_inv = iv
            e.maxru = best_u
            e.min_inv = best_inv if best_inv is not None else 0.0
        e.tdaeub = self.tight_upper_bound(node, e, f, ltid, weights=weights)

    @staticmethod
    def tight_upper_bound(
        node: DAENode,
        e: DAEEntry,
        f: float,
        ltid: int,
        weights: dict[int, float] | None = None,
        w: float | None = None,
    ) -> float:
        """TDAEUB theo 3 trường hợp (semantics PDF § Pha 2 bước 4).

        - TH1 (k == 0): không còn mục nào sau pattern -> 0.
        - TH2 (không có thông tin còn lại): dùng dae.
        - TH3 (còn lại): (u + maxru) / ((Inv + minInv) * (|X|+1)) * w.
          Đây là ae của phần mở rộng 1-mục tốt nhất — chặn trên mọi extension
          dài hơn vì |Y|>=|X|+1. VD order a<b<c: STDAEUB(a)~0.17<0.2 (cắt),
          STDAEUB(b)~0.28>=0.2 (mở rộng {b}x{c}), STDAEUB(c)=0.
        """
        w = HAEIMDampedMiner._resolve_weight(e, f, ltid, weights, w)
        if e.k == 0:
            return 0.0
        if e.maxru <= 0 or e.min_inv <= 0 or node.inv <= 0:
            return e.dae
        plen = len(node.pattern) if node.pattern else 1
        return (e.u + e.maxru) / ((node.inv + e.min_inv) * (plen + 1)) * w

    # ------------------------------------------------- PHA 3: EXPANSION
    def expansion(
        self,
        candidates: list[DAENode],
        f: float,
        minae: float,
        weights: dict[int, float] | None = None,
        _stats: dict | None = None,
    ) -> list[dict]:
        """DFS đệ quy sinh pattern dài hơn từ các DAE-List đã lọc & sắp xếp.

        Đúng PDF § Pha 3:
          1. Sdae(P) >= minae -> thêm vào DHAEIs.
          2. STDAEUB(P) < minae -> cắt cả nhánh.
          3. Ngược lại ghép P với các DAE-List đứng sau (cùng tiền tố),
             dùng LTDAEUB bên trong _join để dừng sớm phép ghép vô vọng.

        Tối ưu: tái dùng bảng `weights` tiền tính; gom thống kê vào `_stats`
        (số lần ghép, thành công, cắt LTDAEUB) để báo cáo mà không tốn thêm pass.
        """
        minae = _validate_minae(minae)
        with self._lock:
            self.extra_nodes.clear()
            results: list[dict] = []
            ltid = self.ltid
            if weights is None:
                weights = self._decay_weights(f, ltid)
            stats = _stats if _stats is not None else {}
            stats["join_attempts"] = stats.get("join_attempts", 0)
            stats["join_success"] = stats.get("join_success", 0)
            stats.setdefault("pruned_stdaeub", 0)

            def emit(node: DAENode) -> None:
                if node.sdae >= minae:
                    results.append(
                        {"pattern": list(node.pattern), "sdae": _round4(node.sdae),
                         "smdaeub": _round4(node.smdaeub), "stdaeub": _round4(node.stdaeub)}
                    )

            def dfs(node: DAENode, cond: list[DAENode]) -> None:
                emit(node)
                # Cắt tỉa AN TOÀN: sbound là cận trên âm cho Sdae của mọi phần
                # mở rộng của node ⇒ sbound < minae ⇒ chắc chắn không có phần
                # mở rộng nào là HAEI (không bỏ sót kết quả).
                if self.sound:
                    if node.sbound < minae:
                        stats["pruned_stdaeub"] = stats.get("pruned_stdaeub", 0) + 1
                        return
                elif node.stdaeub < minae:
                    # bản cũ (không âm): cắt theo STDAEUB của PDF
                    stats["pruned_stdaeub"] = stats.get("pruned_stdaeub", 0) + 1
                    return
                # Sinh toàn bộ extensions cùng cấp của node trước...
                exts: list[DAENode] = []
                for other in cond:
                    stats["join_attempts"] += 1
                    joined = self._join(node, other, f, ltid, minae, weights=weights)
                    if joined is None:
                        continue
                    stats["join_success"] += 1
                    self.extra_nodes[tuple(joined.pattern)] = joined
                    exts.append(joined)
                # ...rồi đệ quy từng extension với các siblings đứng sau nó
                # (cùng độ dài, cùng tiền tố) để sinh pattern dài k+2, k+3...
                for k, ext in enumerate(exts):
                    dfs(ext, exts[k + 1:])

            # root: mỗi singleton làm gốc, cond = các singleton đứng sau nó
            for i, node in enumerate(candidates):
                dfs(node, candidates[i + 1:])
            # khử trùng lặp (giữ Sdae lớn nhất); pattern đã chuẩn tắc theo order
            # nên key chuẩn là tuple(pattern), không sort lại kiểu từ điển.
            uniq: dict[tuple[str, ...], dict] = {}
            for r in results:
                k = tuple(r["pattern"])
                if k not in uniq or r["sdae"] > uniq[k]["sdae"]:
                    uniq[k] = r
            self.results = sorted(uniq.values(), key=lambda r: (len(r["pattern"]), r["pattern"]))
            return self.results

    def _join(
        self,
        px: DAENode,
        py: DAENode,
        f: float,
        ltid: int,
        minae: float,
        weights: dict[int, float] | None = None,
        tx_sets: dict[int, set] | None = None,
    ) -> DAENode | None:
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

        Tối ưu: entries của mỗi node đã được sắp xếp theo tid tại Restructure
        (và node join mới sinh cũng append theo thứ tự merge), nên ghép bằng
        2 con trỏ O(n+m) trong 1 pass duy nhất: vừa tìm tid chung, vừa trừ
        LTDAEUB cho tid lệch — đúng mô tả "hai con trỏ" trong PDF, không tạo
        dict/set trung gian.
        """
        if len(px.pattern) != len(py.pattern):
            return None
        # kiểm tra cùng tiền tố (theo thứ tự order): px[:-1] == py[:-1]
        if len(px.pattern) > 1 and tuple(px.pattern[:-1]) != tuple(py.pattern[:-1]):
            return None
        # pattern mới: giữ thứ tự order để remaining/TDAEUB nhất quán
        new_items = sorted(set(px.pattern) | set(py.pattern),
                           key=lambda it: (self.order_index.get(it, 9999), it))
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
        xe = px.entries
        ye = py.entries
        if not xe or not ye:
            return None
        if weights is None:
            weights = self._decay_weights(f, ltid)
        # 1 pass 2 con trỏ: i trên Px, j trên Py (entries đã sort theo tid)
        i = j = 0
        # LTDAEUB âm: khởi tạo = cận trên âm của Px (sbound), trừ dần đóng góp
        # của các tid chỉ Px có → còn lại là cận trên âm trên các tid chung,
        # vẫn >= Sdae(Pxy) ⇒ dừng sớm là an toàn.
        # (bản không âm dùng STDAEUB/TDAEUB của PDF — nhanh hơn nhưng có thể
        #  bỏ sót HAEI, chỉ dùng để đối chiếu thực nghiệm)
        ltdaeub = px.sbound if self.sound else px.stdaeub
        common_pairs: list[tuple[DAEEntry, DAEEntry]] = []
        while i < len(xe) and j < len(ye):
            ti, tj = xe[i].tid, ye[j].tid
            if ti == tj:
                common_pairs.append((xe[i], ye[j]))
                i += 1
                j += 1
            elif ti < tj:
                # tid chỉ Px có -> trừ LTDAEUB, dừng sớm ngay trong pass
                ltdaeub -= xe[i].sbnd if self.sound else xe[i].tdaeub
                if ltdaeub < minae:
                    return None
                i += 1
            else:
                j += 1
        # vét tid Px còn lại phía sau
        while i < len(xe):
            ltdaeub -= xe[i].sbnd if self.sound else xe[i].tdaeub
            if ltdaeub < minae:
                return None
            i += 1
        if not common_pairs:
            return None
        if ltdaeub < minae:
            return None
        # PU của tiền tố: tra trực tiếp khi cần (prefix rỗng với singleton -> 0)
        node = DAENode(pattern=new_pattern, inv=new_inv, pi=pi)
        sdae = 0.0
        smdaeub = 0.0
        plen = len(new_pattern)
        for ex, ey in common_pairs:
            tid = ex.tid
            pu = self.utility_of(prefix, tid) if prefix else 0.0
            u = ex.u + ey.u - pu
            ae = u / (new_inv * plen) if new_inv and plen else 0.0
            eff = u / new_inv if new_inv else 0.0
            w = weights.get(tid, 0.0)
            dae = ae * w
            mdaeub = eff * w
            sdae += dae
            smdaeub += mdaeub
            node.entries.append(
                DAEEntry(tid=tid, u=u, ae=ae, maeub=eff, pu=pu, dae=dae, mdaeub=mdaeub)
            )
        node.sdae = sdae
        node.smdaeub = smdaeub
        # cận trên âm cho node mới (dùng cho cắt tỉa ở các lần mở rộng sau)
        if self.sound:
            self._apply_sound_bounds(node, weights, minae)
        else:
            node.sbound = 0.0
        # Cận trên kiểu PDF (TDAEUB 1-phần-mở-rộng) chỉ phục vụ HIỂN THỊ →
        # không tính trong đường ghép nóng (tốn O(|R|) cho mỗi entry). Khi cần
        # xem, gọi `compute_paper_bounds(node)` (API /api/dae-lists tự gọi).
        # LƯU Ý: chế độ legacy (sound=False) LẠI dùng cận này để cắt tỉa → phải
        # tính tại đây.
        if not self.sound:
            self.compute_paper_bounds(node)
        return node

    def compute_paper_bounds(self, node: DAENode) -> None:
        """Tính các trường cận trên kiểu PDF (maxru/minInv/k/TDAEUB/STDAEUB).

        Dùng khi **hiển thị** DAE-List. Không dùng để cắt tỉa (bản đó không
        âm — xem `app/core/bounds.py`).
        """
        f = self._last_f
        ltid = self.ltid
        weights = self._decay_weights(f, ltid)
        tx_sets = {tid: set(t) for tid, t in self.transactions.items()}
        std = 0.0
        for e in node.entries:
            self._fill_tight_fields(node, e, f, ltid, weights=weights, tx_sets=tx_sets)
            std += e.tdaeub
        node.stdaeub = std

    # ------------------------------------------------- tiện ích tổng hợp
    def bulk_construction(self, batch: list[tuple[int, list[tuple[str, float]]]]) -> list[int]:
        """Nạp hàng loạt nhiều giao dịch trong 1 lần gọi — tối ưu streaming.

        Tương đương gọi `construction` cho từng tid, nhưng validate toàn lô
        trước (atomic: lỗi 1 tid thì không ghi tid nào) và chỉ chạm cache 1 lần.
        Dùng cho `POST /api/transactions/bulk` để giảm round-trip.
        """
        with self._lock:
            if not batch:
                raise ValueError("Danh sách rỗng")
            # validate toàn lô trước khi ghi (atomic)
            seen: set[int] = set()
            for tid, items in batch:
                if not isinstance(tid, int) or tid <= 0:
                    raise ValueError(f"tid phải là số nguyên > 0, nhận {tid!r}")
                if tid in seen:
                    raise ValueError(f"tid {tid} lặp trong batch")
                seen.add(tid)
                if tid in self.transactions:
                    raise ValueError(f"tid {tid} đã tồn tại")
                if not items:
                    raise ValueError("Transaction rỗng trong batch")
                for item, qty in items:
                    if item not in self.eu or item not in self.inv_table:
                        raise KeyError(f"item '{item}' chưa đăng ký EU/INV")
                    if float(qty) <= 0:
                        raise ValueError("qty phải > 0")
            tids: list[int] = []
            for tid, items in batch:
                self._construct_locked(tid, items)
                tids.append(tid)
            self.extra_nodes.clear()
            self._version += len(tids)
            self._mine_cache = None
            self._mine_cache_key = None
            return tids

    def mine(self, f: float, minae: float) -> dict:
        """Chạy trọn Restructure + Expansion (giữ Construction đã tích lũy).

        Tối ưu: cache theo (f, minae, ltid, số GD, version luồng). Mine lặp lại
        với cùng tham số mà luồng không đổi sẽ trả cache O(1) kèm `cached: True`
        và `stats` lần chạy gốc — đúng cho frontend poll liên tục.
        """
        f = _validate_decay(f)
        minae = _validate_minae(minae)
        with self._lock:
            if not self.transactions:
                raise ValueError("Luồng rỗng")
            # cache-key phải gồm cả chế độ cắt tỉa: đổi sound=True/False cho
            # cùng (f, minae) là kết quả KHÁC nhau → không được dùng cache cũ.
            key = (round(float(f), 6), round(float(minae), 6), self.ltid,
                   len(self.transactions), self._version, self.sound)
            if self._mine_cache_key == key and self._mine_cache is not None:
                out = copy.deepcopy(self._mine_cache)
                out["cached"] = True
                return out
            t0 = time.perf_counter()
            # gọi nội bộ (RLock cho phép restructure/expansion lồng nhau)
            weights = self._decay_weights(f, self.ltid)
            cands = self.restructure(f, minae, weights=weights)
            stats: dict = {"ltid": self.ltid, "transactions": len(self.transactions),
                           "candidates": len(cands)}
            dhaeis = self.expansion(cands, f, minae, weights=weights, _stats=stats)
            stats.setdefault("pruned_stdaeub", 0)
            stats["dhaeis"] = len(dhaeis)
            stats["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            self.last_stats = dict(stats)
            out = {
                "f": f, "ltid": self.ltid, "minae": minae,
                "order": list(self.order),
                "candidates": [
                    {"pattern": list(n.pattern), "sdae": _round4(n.sdae),
                     "smdaeub": _round4(n.smdaeub), "stdaeub": _round4(n.stdaeub)}
                    for n in cands
                ],
                # copy nhẹ (dict mới) — cache giữ bản gốc, trả về là bản sao sâu
                "dhaeis": [dict(d) for d in dhaeis],
                "stats": dict(stats),
                "cached": False,
            }
            self._mine_cache = out
            self._mine_cache_key = key
            return copy.deepcopy(out)

    def reset(self) -> None:
        with self._lock:
            self._clear_locked()
            self._version += 1

    def load_example_stream(self) -> None:
        """Nạp lại luồng mẫu Bảng 1 của PDF (kèm bảng EU/INV/CU gốc).

        Khôi phục **cả bảng chi phí** về giá trị gốc: nếu trước đó đã nạp bộ
        dữ liệu khác (vd thực nghiệm), các mục của PDF (a..f) có thể không còn
        trong bảng → luồng mẫu sẽ không dựng được.
        """
        with self._lock:
            self._clear_locked()
            self.eu = dict(EU)
            self.inv_table = dict(INV)
            self.cu = dict(CU)
            for tid in sorted(EXAMPLE_STREAM):
                # construction cũng dùng lock (RLock nên an toàn khi lồng)
                self._construct_locked(tid, [(i, q) for i, q in EXAMPLE_STREAM[tid]])
                self._version += 1
            self._mine_cache = None
            self._mine_cache_key = None

    # ------------------------------------------------- NẠP BỘ DỮ LIỆU MỚI
    def load_dataset(
        self,
        transactions: dict[int, dict[str, float]],
        eu: dict[str, float],
        inv_table: dict[str, float],
        cu: dict[str, float] | None = None,
    ) -> int:
        """Thay toàn bộ luồng + bảng chi phí bằng một bộ dữ liệu mới.

        Dùng khi nạp dữ liệu thực nghiệm (CSV, bộ sinh tổng hợp) — khác
        `reset()` ở chỗ **thay cả bảng EU/INV/CU** và nạp lại luồng.

        Trả về số giao dịch đã nạp. Toàn bộ thao tác atomic: nếu dữ liệu lỗi
        thì trạng thái cũ giữ nguyên (validate trước khi ghi).
        """
        if not transactions:
            raise ValueError("Bộ dữ liệu rỗng")
        with self._lock:
            # --- validate toàn bộ TRƯỚC khi đụng trạng thái (atomic) ---
            norm: dict[int, dict[str, float]] = {}
            for tid, tmap in transactions.items():
                if not isinstance(tid, int) or tid <= 0:
                    raise ValueError(f"tid phải là số nguyên > 0, nhận {tid!r}")
                clean: dict[str, float] = {}
                for item, qty in tmap.items():
                    item = str(item).strip()
                    if not item:
                        raise ValueError("item rỗng")
                    if item not in eu or item not in inv_table:
                        raise ValueError(
                            f"item '{item}' thiếu EU/INV — cần định nghĩa cho mọi mục"
                        )
                    if float(qty) <= 0:
                        raise ValueError(f"qty phải > 0 (item '{item}')")
                    clean[item] = clean.get(item, 0.0) + float(qty)
                if not clean:
                    raise ValueError(f"Giao dịch tid={tid} rỗng")
                norm[tid] = clean
            if not eu:
                raise ValueError("Bảng EU rỗng")
            if not inv_table:
                raise ValueError("Bảng INV rỗng")
            # eu/inv phải dương — nếu không, `ae = u/(Inv·|X|)` chia tay / cho
            # hiệu suất âm và phá vỡ mọi cận trên (bắt lỗi sớm, trước khi ghi).
            for name, tbl in (("EU", eu), ("INV", inv_table)):
                for k, v in tbl.items():
                    if float(v) <= 0:
                        raise ValueError(f"{name}({k!r}) phải > 0, nhận {v!r}")

            # --- ghi ---
            self._clear_locked()
            self.eu = {str(k): float(v) for k, v in eu.items()}
            self.inv_table = {str(k): float(v) for k, v in inv_table.items()}
            self.cu = {str(k): float(v) for k, v in (cu or {}).items()}
            for tid in sorted(norm):
                self._construct_locked(tid, sorted(norm[tid].items()))
            self._version += 1
            self._mine_cache = None
            self._mine_cache_key = None
            return len(norm)
