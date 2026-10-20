# Kiến trúc hệ thống & phân tích độ phức tạp

> Tài liệu kỹ thuật đi kèm mã nguồn. Dùng cho chương "Phân tích thiết kế" của
> luận văn và để tra cứu nhanh khi sửa code.

## 1. Sơ đồ kiến trúc tổng thể

```
                    ┌──────────────────────────────────────────┐
   HTTP (JSON)      │            app/main.py (FastAPI)         │
   ───────────────► │  nhóm endpoint: luồng / khai thác /        │
                    │  kiểm chứng / thực nghiệm / dữ liệu /     │
                    │  giải thích / chỉ số                       │
                    └───────────────┬──────────────────────────┘
                                    │ (chỉ gọi hàm công khai)
        ┌───────────────────────────┼────────────────────────────┐
        ▼                           ▼                            ▼
┌───────────────┐        ┌──────────────────┐        ┌───────────────────┐
│ app/core/     │        │ app/core/        │        │ app/core/         │
│ haeim_damped  │        │ baseline.py      │        │ bench.py          │
│ (THUẬT TOÁN)  │        │ (GROUND TRUTH)   │        │ (ĐO ĐẠC)          │
│               │        │                  │        │                   │
│ Construction  │        │ duyệt MỌI tập mục│       │ benchmark         │
│ Restructure   │        │ con của mọi GD   │       │ scalability       │
│ Expansion     │        │ O(Σ 2^|T_j|)     │       │ sweep             │
└───────┬───────┘        └────────┬─────────┘        │ pruning compare   │
        │                         │                  └───────────────────┘
        │ uses                    │ dùng để
        ▼                         ▼
┌───────────────────┐     ┌────────────────────┐      ┌────────────────────┐
│ app/core/bounds.py│     │ app/core/datasets  │      │ app/core/explain   │
│ CẬN TRÊN ÂM       │     │ sinh dữ liệu, CSV  │      │ truy vết "vì sao"  │
│ (chứng minh)     │     │                    │      │                    │
└───────────────────┘     └────────────────────┘      └────────────────────┘
        ▲
        │ import
┌───────┴───────┐
│ app/core/data │  Bảng 1 (luồng mẫu), Bảng 2 (chi phí), tham số mặc định
└───────────────┘
```

**Nguyên tắc phân tách:**

| Module | Trách nhiệm | Phụ thuộc |
|---|---|---|
| `haeim_damped.py` | Thuật toán 3 pha (trái tim hệ thống) | `bounds`, `data` |
| `bounds.py` | Cận trên âm + chứng minh tính đúng | — (độc lập) |
| `baseline.py` | Ground truth — **không dùng cắt tỉa** | — (độc lập) |
| `datasets.py` | Sinh dữ liệu, CSV I/O | `data` |
| `bench.py` | Đo đạc, thực nghiệm | `baseline`, `datasets`, `haeim_damped` |
| `explain.py` | Truy vết kết quả | `haeim_damped` |
| `main.py` | Lớp HTTP | tất cả |

> `baseline.py` và `bounds.py` **không import** `haeim_damped.py` → ground truth
> độc lập với thuật toán, đảm bảo phép so sánh có ý nghĩa.

## 2. Cấu trúc dữ liệu

### 2.1. DAE-List (2 cấp)

```
DAENode                                  DAEEntry
(pattern: tuple[str,...])                (tid, u, ae, maeub, pu,
 inv, pi, sdae, smdaeub, stdaeub,         dae, mdaeub, maxru, min_inv,
 sbound                                  k, tdaeub, sbnd)
 entries: list[DAEEntry])
```

| Trường | Ý nghĩa | Ghi chú |
|---|---|---|
| `sdae` | Tổng hiệu suất trung bình suy giảm | **quyết định HAEI** (`sdae >= minae`) |
| `smdaeub` | Cận trên kiểu PDF (MAEUB) | hiển thị, đối chiếu PDF |
| `stdaeub` | Cận trên 1-phần-mở-rộng (PDF) | hiển thị, **không dùng cắt tỉa** |
| `sbound` | **Cận trên âm** (Σ sbnd·w) | **dùng cắt tỉa — an toàn** |
| `sbnd` (entry) | Cận trên âm cấp giao dịch | `max_{Z⊆R} ae(X∪Z, Tj)·w` |

### 2.2. Chỉ mục phụ trợ `TxIndex`

Dựng 1 lần mỗi lần Restructure, phục vụ tính cận trên âm:

- `by_u`: mục theo tiện ích giảm dần (+ `u_vals` song song)
- `by_v`: mục theo chi phí đầu tư tăng dần (+ `v_vals` song song)

Từ 2 thứ tự này suy ra ngay:
- `U_max(m)` = tổng tiện ích `m` mục lớn nhất còn lại → prefix sum
- `I_min(m)` = tổng chi phí `m` mục rẻ nhất còn lại → prefix sum

→ tính cận trên âm trong `O(|T_j|)` cho mỗi entry, không cần sắp xếp lại.

## 3. Phân tích độ phức tạp

Ký hiệu: `N` = số giao dịch, `B` = độ dài giỏ hàng trung bình, `M` = số mục,
`P` = số pattern được sinh, `K` = số ứng viên sau lọc.

| Pha | Độ phức tạp | Ghi chú |
|---|---|---|
| **1. Construction** | `O(N·B·log B)` | sort 1 lần/GD; **không quét lại dữ liệu cũ** |
| **2. Restructure** | `O(N·B·M)` | áp suy giảm + cận trên âm cho mọi entry |
| **3. Expansion** | `O(P·K + Σ ghép·B)` | DFS + 2 con trỏ cho phép ghép |
| **Ground truth** (đối chiếu) | `O(Σ_j 2^|T_j|)` | **mũ** — đây là lý do cần cắt tỉa |
| Suy giảm | `O(N)` bảng trọng số | tiền tính 1 lần/mine, tra O(1) |
| Ghép 2 node | `O(n_x + n_y)` | 2 con trỏ trên `tidList` đã sort, 1 pass |

### 3.1. Vì sao Construction là O(|T_j|)?

`_construct_locked` chỉ:
1. tạo/ghi entry cho từng mục trong `T_j` (O(|T_j|)),
2. tính MAEUB thô bằng greedy trên thứ tự **đã sort sẵn** của `T_j`.

Không đọc lại `self.transactions`, `self.nodes` cũ → không quét lại luồng.
Kiểm chứng thực nghiệm: `growth_ratio ≈ 0.7` (xem `docs/results/experiments.md`).

### 3.2. Vì sao cần cắt tỉa?

Ground truth duyệt **mọi** tập mục con của mọi giao dịch: `Σ_j 2^|T_j|`.
Với giỏ hàng 12 mục → 4096 tập mục con/giao dịch; 1000 giao dịch → 4,1 triệu
tập mục. HAEIM_Damped chỉ thử ~120 phép ghép → giảm **4 bậc độ lớn** không
gian tìm kiếm.

## 4. Luồng dữ liệu qua hệ thống

```
T_j mới
   │
   ├─► [Construction] ──► DAE-List cấp cửa sổ (entry thô: u, ae, maeub)
   │        O(|T_j|), không quét lại
   │
   ├─► [Restructure] ───► áp w=f^(Ltid-tid) → Sdae, SMDAEUB
   │        (theo chu kỳ)  lọc ứng viên → sắp xếp → STDAEUB + cận âm
   │
   └─► [Expansion] ─────► DFS sinh pattern dài → tập DHAEIs
            (theo chu kỳ)  ghép theo tiền tố, cắt tỉa bằng cận âm
```

Hai mốc "chu kỳ" (Restructure + Expansion) được kích hoạt bằng `POST /api/mine`.
Giữa hai mốc, dữ liệu chỉ **tích lũy** (Pha 1) — đúng mô hình luồng của bài báo.

## 5. Cơ chế an toàn của phép cắt tỉa

Đây là phần **quan trọng nhất** về mặt học thuật. Xem `app/core/bounds.py`
cho đầy đủ. Tóm tắt:

> **Định lý.** Với mọi tập mục Y ⊇ X và mọi Tj chứa Y:
> `Sdae(Y) ≤ Σ_{Tj ∋ X} B(X,Tj)·w` — trong đó `B(X,Tj)` là cận trên của
> `ae(Y,Tj)`.
>
> **Hệ quả.** Nếu `sbound(X) = Σ B(X,Tj)·w < minae` thì **không** tập mục
> nào mở rộng X có thể là HAEI → cắt cả nhánh là **an toàn**.

Chứng minh `B(X,Tj) ≥ ae(Y,Tj)`: với `Z = Y \ X`, `m = |Z|`,
`u(Y) = u(X)+U_Z ≤ u(X)+U_max(m)` và `Inv(Y) = Inv(X)+I_Z ≥ Inv(X)+I_min(m)`
nên `eff(Y) ≤ bound_m`, và `ae(Y) = eff(Y)/(|X|+m) ≤ bound_m/(p+m)`.
Lấy max theo `m` cho cận trên âm.

**Hệ quả thực hành:** mọi phép cắt tỉa đều dựa trên cận trên âm ⇒ thuật toán
**không bao giờ bỏ sót HAEI**. Đây là điều được kiểm chứng tự động bằng
`tests/test_ground_truth.py` (30 luồng ngẫu nhiên) và `POST /api/validate`.

## 6. Quyết định thiết kế đã đánh đổi

| Quyết định | Lý do | Hệ quả |
|---|---|---|
| Cận trên âm thay cho cận 1-phần-mở-rộng | bản PDF bỏ sót HAEI ở quy mô lớn | chậm hơn ~1.3–2×, đúng tuyệt đối |
| `EXACT_SUBSET_LIMIT = 6` | điểm cân bằng đo được giữa cận chặt & tốc độ | xem bảng trong `bounds.py` |
| Cận "kiểu PDF" tính **lazy** | chỉ dùng để hiển thị | đường ghép nóng nhanh hơn ~1.9× |
| Ground truth duyệt tập mục con của từng GD | chỉ tập mục có mặt trong GD mới có Sdae ≠ 0 | độ phức tạp `O(Σ2^|T_j|)` thay vì `O(2^M)` |
| Bộ sinh dữ liệu có **hiệu chuẩn thang đo** | `minae=0.2` chỉ có ý nghĩa ở thang đo của PDF | dữ liệu tổng hợp rơi vào vùng làm việc |

## 7. Định hướng mở rộng

1. **Song song hoá Pha 2/3**: Restructure+Expansion có thể chạy nền (thread pool)
   vì đã bảo đảm `RLock`; hiện `mine()` chạy đồng bộ.
2. **Cận trên âm chặt hơn**: dùng ràng buộc "tỉ lệ hiệu suất" (Dinkelbach) thay vì
   ghép `U_max`/`I_min` độc lập → giảm độ lỏng, tăng tỉ lệ cắt tỉa.
3. **Cận trên theo ngưỡng**: cắt theo `sbound` đã dùng; có thể dùng cận theo
   *phân phối* (ví dụ cận trên dựa trên `Sdae` của các entry lớn nhất) để cắt
   sớm hơn nữa mà vẫn âm.
4. **Dữ liệu thật**: nạp CSV basket thực tế (vd UCI Online Retail) để đo trên
   phân phối thật.
5. **Xuất báo cáo PDF/LaTeX** từ `docs/results/experiments.json` để đưa thẳng
   vào phụ lục luận văn.
