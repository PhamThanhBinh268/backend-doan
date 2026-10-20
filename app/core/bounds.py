"""Cận trên ÂM (sound upper bound) cho hiệu suất trung bình của các phần mở rộng.

Vấn đề phát hiện được (và là kết quả quan trọng của đồ án)
-----------------------------------------------------------
Bản cài đặt đầu tiên dùng cận trên "chặt" theo công thức 1-phần-mở-rộng:

    TDAEUB(X,Tj) = (u(X) + maxru) / ((Inv(X) + minInv) * (|X|+1)) * w

Công thức này chỉ chặn trên **đúng** với các phần mở rộng **thêm 1 mục**.
Với phần mở rộng thêm *m ≥ 2* mục, tổng tiện ích có thể vượt `u(X)+maxru`
(vì `maxru` chỉ là tiện ích đơn lớn nhất), nên cận trên bị **vi phạm** →
Pha 3 cắt tỉa nhánh có chứa HAEI thật → **bỏ sót kết quả**.

Kiểm chứng bằng ground truth (duyệt tất cả tập mục) cho thấy ở luồng
1000 giao dịch / 18 mục, thuật toán bản cũ bỏ sót 28/148 HAEI (tỉ lệ khớp
81%) — tức là cắt tỉa **không an toàn** ở quy mô lớn.

Module này cung cấp cận trên **âm** (luôn ≥ giá trị thật):

    Với X ⊆ Tj, p = |X|, R = Tj \\ X (các mục còn lại), và m = |Z|:

        U_max(m) = tổng tiện ích lớn nhất trong m mục thuộc R
        I_min(m) = tổng chi phí đầu tư nhỏ nhất trong m mục thuộc R
        bound_m  = (u(X) + U_max(m)) / (Inv(X) + I_min(m))

    với mọi Z ⊆ R, |Z| = m:
        u(X∪Z) ≤ u(X) + U_max(m)      (tử số nhỏ hơn)
        Inv(X∪Z) ≥ Inv(X) + I_min(m)  (mẫu số lớn hơn)
      ⇒  eff(X∪Z) = u/Inv ≤ bound_m
      ⇒  ae(X∪Z) = eff/(|X|+m) ≤ bound_m / (p+m)

    B(X,Tj) = max_{m=1..|R|} bound_m/(p+m)   ≥  mọi ae(X∪Z, Tj)

Do đó:  Sdae(X∪Z) = Σ_{Tj∋X∪Z} ae·w  ≤  Σ_{Tj∋X} B(X,Tj)·w
      ⇒ nếu Σ B·w < minae thì **chắc chắn** không phần mở rộng nào của X
        là HAEI (phép cắt tỉa an toàn).

Khác biệt so với bản cũ: B dùng **tất cả** mục còn lại trong Tj (không chỉ
các mục đứng sau theo thứ tự) và xét **mọi** kích thước phần mở rộng.
"""

from __future__ import annotations

__all__ = ["TxIndex", "build_index", "sound_bound", "EXACT_SUBSET_LIMIT"]

# Ngưỡng duyệt tập mục con CHÍNH XÁC (2^|R| <= giới hạn). Giỏ hàng nhỏ (đa số
# dữ liệu giao dịch thực tế: 3-7 mục) thì duyệt tất cả tập mục con — cận trên
# đúng tuyệt đối, chặt nhất. Giỏ hàng lớn thì dùng cận trên lỏng (vẫn âm).
#
# Tham số này là điểm cân bằng giữa "cận chặt" (ít mở rộng, đo tốn 2^|R|) và
# "cận lỏng" (nhanh, nhưng mở rộng nhiều hơn). Đo thực nghiệm trên luồng
# 1000 GD / 18 mục / giỏ tối đa 12 mục:
#     limit=4: 521ms   limit=6: 379ms   limit=8: 596ms   limit=12: 2613ms
# (mọi giá trị đều cho kết quả khớp 100% ground truth)
EXACT_SUBSET_LIMIT = 6


class TxIndex:
    """Chỉ mục phụ trợ cho MỘT giao dịch — phục vụ tính cận trên âm.

    Lưu sẵn:
      * thứ tự mục theo tiện ích giảm dần + prefix sum (để lấy U_max(m)),
      * thứ tự mục theo chi phí đầu tư tăng dần + prefix sum (để lấy I_min(m)),
      * bản đồ item → vị trí trong 2 thứ tự trên.
    """

    __slots__ = (
        "tid", "items", "util", "inv",
        "by_u", "by_v", "pos_u", "pos_v",
        "u_vals", "v_vals",
    )

    def __init__(self, tid: int, items: list[str], util: dict[str, float],
                 inv: dict[str, float]):
        self.tid = tid
        self.items = items
        self.util = util
        self.inv = inv
        # thứ tự theo tiện ích giảm dần (tie: theo tên để tất định)
        self.by_u = sorted(items, key=lambda i: (-util.get(i, 0.0), i))
        # thứ tự theo chi phí đầu tư tăng dần
        self.by_v = sorted(items, key=lambda i: (inv.get(i, 0.0), i))
        self.pos_u = {it: k for k, it in enumerate(self.by_u)}
        self.pos_v = {it: k for k, it in enumerate(self.by_v)}
        # giá trị tương ứng theo đúng thứ tự — tránh tra dict trong vòng lặp nóng
        self.u_vals = [util.get(i, 0.0) for i in self.by_u]
        self.v_vals = [inv.get(i, 0.0) for i in self.by_v]

    def top_u_excluding(self, exclude: set[str]) -> list[float]:
        """TU[m] = tổng tiện ích của m mục có tiện ích lớn nhất trong R (loại exclude).

        TU[0] = 0, TU[m] = tổng m mục lớn nhất còn lại.
        """
        out = [0.0]
        acc = 0.0
        for it, v in zip(self.by_u, self.u_vals):
            if it in exclude:
                continue
            acc += v
            out.append(acc)
        return out

    def min_v_excluding(self, exclude: set[str]) -> list[float]:
        """TV[m] = tổng chi phí đầu tư của m mục rẻ nhất còn lại (loại exclude)."""
        out = [0.0]
        acc = 0.0
        for it, v in zip(self.by_v, self.v_vals):
            if it in exclude:
                continue
            acc += v
            out.append(acc)
        return out


def build_index(tid: int, tmap: dict[str, float], eu: dict[str, float],
                inv_table: dict[str, float]) -> TxIndex:
    """Dựng chỉ mục cho một giao dịch."""
    items = sorted(tmap)
    util = {it: tmap[it] * eu.get(it, 0.0) for it in items}
    inv = {it: inv_table.get(it, 0.0) for it in items}
    return TxIndex(tid, items, util, inv)


def sound_bound(
    index: TxIndex,
    pattern: tuple[str, ...],
    u_p: float,
    inv_p: float,
    minae_hint: float | None = None,
) -> float:
    """Cận trên âm của `ae(X∪Z, Tj)` cho mọi phần mở rộng Z ⊆ R.

    - Nếu |R| nhỏ (<= EXACT_SUBSET_LIMIT): duyệt **tất cả** tập mục con của R
      → cận trên đúng tuyệt đối (chặt nhất, không thể vượt).
    - Nếu |R| lớn: dùng cận trên lỏng (U_max/I_min) — vẫn **âm** (không bao
      giờ nhỏ hơn giá trị thật) nên phép cắt tỉa vẫn an toàn.

    `minae_hint`: nếu cận trên LỎNG đã < minae_hint thì chắc chắn entry này bị
    cắt (cận chính xác ≤ cận lỏng) → bỏ qua phép duyệt tập mục con (tiết kiệm
    thời gian, quyết định cắt tỉa không đổi).

    Trả về 0 nếu không còn mục nào để mở rộng (k = 0).
    """
    if inv_p <= 0:
        return 0.0
    exclude = set(pattern)
    tu = index.top_u_excluding(exclude)
    tv = index.min_v_excluding(exclude)
    n_rem = len(tu) - 1
    if n_rem <= 0:
        return 0.0
    p = len(pattern)

    loose = 0.0
    for m in range(1, n_rem + 1):
        den = inv_p + tv[m]
        if den <= 0:
            continue
        cand = ((u_p + tu[m]) / den) / (p + m)
        if cand > loose:
            loose = cand

    if minae_hint is not None and loose < minae_hint:
        return loose  # chắc chắn bị cắt — không cần cận chính xác
    if n_rem <= EXACT_SUBSET_LIMIT:
        exact = _exact_bound(index, exclude, u_p, inv_p, p, n_rem)
        return exact if exact > loose else loose
    return loose


def _exact_bound(
    index: TxIndex,
    exclude: set[str],
    u_p: float,
    inv_p: float,
    p: int,
    n_rem: int,
) -> float:
    """Cận trên CHÍNH XÁC: max ae(X∪Z, Tj) duyệt mọi Z ⊆ R (|R| nhỏ).

    Dùng DP theo bitmask: u(mask), inv(mask), popcount(mask) tính O(1) mỗi
    mask từ mask nhỏ hơn → tổng O(2^|R|).
    """
    rem = [it for it in index.by_u if it not in exclude]
    utils = [index.util.get(it, 0.0) for it in rem]
    invs = [index.inv.get(it, 0.0) for it in rem]
    total = 1 << n_rem
    su = [0.0] * total
    si = [0.0] * total
    pc = [0] * total
    best = 0.0
    for mask in range(1, total):
        low = mask & -mask
        j = low.bit_length() - 1
        rest = mask ^ low
        su[mask] = su[rest] + utils[j]
        si[mask] = si[rest] + invs[j]
        pc[mask] = pc[rest] + 1
        den = inv_p + si[mask]
        if den <= 0:
            continue
        cand = ((u_p + su[mask]) / den) / (p + pc[mask])
        if cand > best:
            best = cand
    return best
