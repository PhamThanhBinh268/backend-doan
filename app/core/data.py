"""Static data suy ra từ PDF TongHop_LuongXuLy_HAEIM_Damped.pdf.

Bảng 1 — luồng giao dịch (Tid, [(item, qty)], [utility từng item], TU).
Bảng 2 — cu(i) (chi phí đơn vị) và inv(i) (chi phí đầu tư tĩnh của mục).

Suy luận đã kiểm chứng bằng code (xem README):
- Ngoại tiện ích eu(i) = utility / qty, ổn định trên mọi giao dịch:
    a=4, b=3, c=5, d=2, e=4, f=2
- inv(i) trong Bảng 2 chính là mẫu số của ae({i}, Tj):
    ae({a}, T1) = 4/96 = 0.0417 khớp 100% Ví dụ 1.
- inv(i) = cu(i) * tổng_qty(i) trên toàn luồng (vd a: 12*8=96).
- Tham số ví dụ xuyên suốt: f=0.8, Ltid=8, minae=0.2
  (khớp Sdae: {a}=0.188, {b}=0.542, {c}=0.598).
"""

from __future__ import annotations

# Ngoại tiện ích (external utility) suy từ Bảng 1: utility / qty
EU = {"a": 4.0, "b": 3.0, "c": 5.0, "d": 2.0, "e": 4.0, "f": 2.0}

# Chi phí đơn vị (Bảng 2)
CU = {"a": 12.0, "b": 3.0, "c": 4.0, "d": 9.0, "e": 13.0, "f": 5.0}

# Chi phí đầu tư tĩnh của mục (Bảng 2) — dùng làm Inv(X) = sum inv(i)
INV = {"a": 96.0, "b": 51.0, "c": 72.0, "d": 162.0, "e": 91.0, "f": 50.0}

# Luồng 8 giao dịch mẫu (Bảng 1): tid -> [(item, qty)]
EXAMPLE_STREAM: dict[int, list[tuple[str, int]]] = {
    1: [("a", 1), ("c", 1), ("d", 2), ("f", 1)],
    2: [("a", 1), ("b", 2), ("c", 2), ("d", 5), ("e", 2), ("f", 6)],
    3: [("a", 1), ("b", 2), ("c", 5), ("e", 1)],
    4: [("b", 4), ("c", 2), ("d", 4), ("e", 1)],
    5: [("b", 2), ("c", 3), ("d", 2), ("e", 1), ("f", 1)],
    6: [("a", 3), ("b", 4), ("c", 2), ("d", 1)],
    7: [("a", 1), ("b", 1), ("c", 2), ("d", 3), ("f", 2)],
    8: [("a", 1), ("b", 2), ("c", 1), ("d", 1), ("e", 2)],
}

# Utility từng item trong từng giao dịch (Bảng 1) — dùng để đối chiếu, không cần tính lại
EXAMPLE_UTILITY = {
    1: {"a": 4, "c": 5, "d": 4, "f": 2},
    2: {"a": 4, "b": 6, "c": 10, "d": 10, "e": 8, "f": 12},
    3: {"a": 4, "b": 6, "c": 25, "e": 4},
    4: {"b": 12, "c": 10, "d": 8, "e": 4},
    5: {"b": 6, "c": 15, "d": 4, "e": 4, "f": 2},
    6: {"a": 12, "b": 12, "c": 10, "d": 2},
    7: {"a": 4, "b": 3, "c": 10, "d": 6, "f": 4},
    8: {"a": 4, "b": 6, "c": 5, "d": 2, "e": 8},
}

EXAMPLE_TU = {1: 15, 2: 50, 3: 39, 4: 34, 5: 31, 6: 36, 7: 27, 8: 25}

# Tham số mặc định khớp mọi ví dụ trong PDF
DEFAULT_F = 0.8
DEFAULT_MINAE = 0.2

# Kết quả kỳ vọng theo PDF với (f=0.8, Ltid=8, minae=0.2):
# {a}:0.188 loại, {b}:0.542 HAEI, {c}:0.598 HAEI, {b,c}:0.2047 HAEI => DHAEIs={b,c,{b,c}}
EXPECTED_SDAE_1ITEM = {"a": 0.188, "b": 0.542, "c": 0.598}
EXPECTED_SMDAEUB = {"a": 0.206, "b": 0.544, "c": 0.598, "d": 0.129, "e": 0.193, "f": 0.171}
