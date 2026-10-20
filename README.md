# HAEIM_Damped — Khai thác tập mục hiệu suất trung bình cao trên luồng suy giảm

> Đồ án tốt nghiệp · Backend FastAPI + Dashboard web · Triển khai đầy đủ 3 pha
> **Construction → Restructure → Expansion** theo bài báo
> `TongHop_LuongXuLy_HAEIM_Damped.pdf`.

```
┌─ Bản đồ dự án ──────────────────────────────────────────────────────────┐
│  HAEIM_Damped  =  thuật toán khai thác  +  mô hình kiểm chứng độ đúng
│                   +  bộ công cụ đo đạc thực nghiệm  +  dashboard trình bày │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 0. Điểm nhấn của dự án (đọc trước)

| # | Đóng góp | Vì sao quan trọng |
|---|---|---|
| 1 | **Ground truth độc lập** (`app/core/baseline.py`) | Duyệt *mọi* tập mục con của *mọi* giao dịch — không dùng bất kỳ cắt tỉa nào — để có "đáp án đúng" đối chiếu. Biến bài toán "cắt tỉa có đúng không?" thành **phép kiểm chứng tự động**. |
| 2 | **Phát hiện lỗi cắt tỉa & sửa bằng cận trên âm** | Cận trên kiểu bài báo (1-phần-mở-rộng) **vi phạm** với phần mở rộng ≥ 2 mục → bỏ sót HAEI ở quy mô lớn (ví dụ: mất `{f,m}` trên luồng 1000 GD). Đã thay bằng **cận trên âm** có chứng minh → khớp 100% ground truth. |
| 3 | **Bộ sinh dữ liệu tái lập được** | Mô phỏng dữ liệu siêu thị (Zipf + trôi thị phần có hồi phục) + hiệu chuẩn thang đo; kèm nhập/xuất CSV để chạy trên dữ liệu thật. |
| 4 | **Công cụ đo đạc thực nghiệm** | Benchmark, quét kích thước, quét tham số, đo chi phí Pha 1, so sánh 2 chiến lược cắt tỉa — tất cả tái lập được bằng 1 lệnh. |
| 5 | **Truy vết "vì sao"** | Mỗi pattern có lý do kết luận đầy đủ (đóng góp từng giao dịch, cận trên đã dùng, lý do bị loại). |
| 6 | **Dashboard 6 màn hình** | Trình bày & bảo vệ luận văn không cần Postman. |

> **Kết quả tiêu biểu** (luồng 1000 GD / 18 mục / giỏ ≤ 12 mục, `f=0.8`, `minae=0.2`):
> cắt tỉa âm tìm đủ **49/49** HAEI (khớp 100% ground truth) trong **0.54 s**,
> nhanh hơn ground truth **9×**; bản cắt tỉa kiểu bài báo chạy nhanh hơn nhưng
> **bỏ sót 1 HAEI**.

---

## 1. Cài đặt & chạy

```bash
cd backend
pip install -r requirements.txt

# API + tài liệu tương tác
uvicorn app.main:app --reload --port 8000
#   Swagger UI : http://localhost:8000/docs
#   Dashboard  : http://localhost:8000/ui

# Chạy test (93 test)
python -m pytest tests -v

# Tái lập toàn bộ số liệu thực nghiệm (ghi ra docs/results/)
python scripts/run_experiments.py          # đầy đủ (~90s)
python scripts/run_experiments.py --quick  # rút gọn (~10s)
```

> **Zero-dependency**: chỉ `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`.
> Biểu đồ vẽ tay bằng SVG, bộ sinh dữ liệu dùng `random` chuẩn → cài đặt
> 1 lệnh, không lo xung đột môi trường khi bảo vệ.

---

## 2. Thuật toán

### 2.1. Định nghĩa

| Ký hiệu | Công thức | Nguồn |
|---|---|---|
| `u(X,Tj)` | `Σ_{i∈X} qty(i,Tj)·eu(i)` | tiện ích tập mục |
| `Inv(X)` | `Σ_{i∈X} INV[i]` | Bảng 2 (tĩnh, **không** nhân qty) |
| `ae(X,Tj)` | `u(X,Tj) / (Inv(X)·|X|)` | **Công thức 5** — hiệu suất *trung bình* |
| `dae` | `ae·f^(Ltid−tid)` | áp suy giảm tại Restructure |
| `Sdae(X)` | `Σ_{Tj∋X} dae` | quyết định HAEI: `Sdae ≥ minae` |

Kiểm chứng: `ae({a},T1) = 4/96/1 = 0.0417` ✓ (Ví dụ 1 PDF);
`Sdae({a})=0.188, {b}=0.542, {c}=0.598` ✓ (Ví dụ 3 PDF, sai số < 0.005).

### 2.2. Ba pha

| Pha | Việc | Độ phức tạp |
|---|---|---|
| **1. Construction** | Nhận `T_j`, ghi `u/ae/MAEUB` **thô** vào DAE-List cấp cửa sổ. Không quét lại dữ liệu cũ. | `O(N·B·log B)` |
| **2. Restructure** | Áp `f^(Ltid−tid)`, lọc ứng viên, sắp xếp tăng dần `SMDAEUB`, tính `Sdae/STDAEUB` + cận trên âm. | `O(N·B·M)` |
| **3. Expansion** | DFS: `Sdae ≥ minae` → HAEI; cắt tỉa bằng cận âm; ghép 2 node cùng tiền tố bằng **2 con trỏ**. | `O(P·K)` |

> **Lưu ý quan trọng (PDF §3):** Construction chỉ lưu `ae/MAEUB` **thô**, vì
> trọng số `f^(Ltid−tid)` phụ thuộc `Ltid` thay đổi liên tục — suy giảm chỉ áp
> tại Restructure. Code: `haeim_damped.py::restructure`.

### 2.3. Cắt tỉa AN TOÀN (đóng góp chính của đồ án)

Bản đầu tiên dùng cận trên kiểu bài báo:

```
TDAEUB(X,Tj) = (u(X)+maxru) / ((Inv(X)+minInv)·(|X|+1)) · w
```

Công thức này chỉ chặn trên **đúng** với phần mở rộng **thêm 1 mục**. Với
phần mở rộng thêm `m ≥ 2` mục, tổng tiện ích có thể vượt `u(X)+maxru`
(`maxru` chỉ là tiện ích **đơn** lớn nhất) ⇒ **cận trên bị vi phạm** ⇒ Pha 3 cắt
cả nhánh chứa HAEI thật ⇒ **bỏ sót kết quả**.

> Kiểm chứng: trên luồng 1000 GD / 18 mục, bản này tìm 48/49 HAEI
> (thiếu `{f,m}`, tỉ lệ khớp 97,96%).

**Cách sửa:** thay bằng **cận trên âm** (`app/core/bounds.py`):

```
Với X ⊆ Tj, p=|X|, R = Tj \ X, m = |Z|:
   U_max(m) = tổng tiện ích lớn nhất của m mục thuộc R
   I_min(m) = tổng chi phí đầu tư nhỏ nhất của m mục thuộc R
   bound_m  = (u(X)+U_max(m)) / (Inv(X)+I_min(m))
   B(X,Tj)  = max_{m=1..|R|} bound_m / (p+m)     ≥ mọi ae(X∪Z, Tj)
```

Vì `u(X∪Z) ≤ u(X)+U_max(m)` và `Inv(X∪Z) ≥ Inv(X)+I_min(m)` nên `B` **không
bao giờ nhỏ hơn giá trị thật**. Suy ra:

```
Sdae(Y) ≤ Σ_{Tj∋X} B(X,Tj)·w = sbound(X)   (mọi phần mở rộng Y ⊇ X)
⇒ sbound(X) < minae  ⇒  chắc chắn không phần mở rộng nào là HAEI
```

→ **mọi phép cắt tỉa đều an toàn**, thuật toán khớp 100% ground truth.
Chứng minh đầy đủ: `docs/ARCHITECTURE.md` §5.

Hai chế độ được hỗ trợ để đối chiếu:

| Chế độ | Cắt tỉa bằng | Đặc tính |
|---|---|---|
| `sound=true` (mặc định) | cận trên âm | **không bỏ sót** HAEI |
| `sound=false` | cận 1-phần-mở-rộng (PDF) | nhanh hơn ~1.3–2×, **bỏ sót** ở quy mô lớn |

---

## 3. Kiến trúc mã nguồn

```
backend/
├── app/
│   ├── main.py              # FastAPI — 30+ endpoint
│   ├── schemas.py           # Pydantic models
│   └── core/
│       ├── haeim_damped.py  # ★ thuật toán 3 pha
│       ├── bounds.py        # ★ cận trên âm + chứng minh
│       ├── baseline.py      # ★ ground truth (độc lập, không cắt tỉa)
│       ├── datasets.py      # sinh dữ liệu + CSV I/O
│       ├── bench.py         # đo đạc & thực nghiệm
│       ├── explain.py       # truy vết "vì sao"
│       └── data.py          # Bảng 1, Bảng 2, tham số mặc định
├── frontend/                # dashboard (Vanilla JS + SVG, không build step)
├── tests/                   # 93 test
├── scripts/run_experiments.py
└── docs/
    ├── ARCHITECTURE.md      # kiến trúc & phân tích độ phức tạp
    ├── DEFENSE.md           # Q&A bảo vệ luận văn
    └── results/             # số liệu thực nghiệm (sinh tự động)
```

> `baseline.py` và `bounds.py` **không import** `haeim_damped.py` → phép so
> sánh với ground truth là độc lập, có ý nghĩa.

Chi tiết kiến trúc & phân tích độ phức tạp: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 4. API

### 4.1. Luồng & khai thác (cốt lõi)

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | trạng thái, `ltid`, số GD, phiên bản, `last_stats` |
| `GET` | `/api/config` | bảng `eu/cu/inv` + tham số mặc định |
| `GET` | `/api/transactions` | danh sách giao dịch hiện tại |
| `POST` | `/api/transactions` | **Pha 1** — thêm `T_j` |
| `POST` | `/api/transactions/bulk` | nạp hàng loạt `T_j` (1 request, atomic) |
| `POST` | `/api/items` | đăng ký mục mới phát sinh trên luồng |
| `POST` | `/api/mine` | **Pha 2+3** — `{f, minae, sound}` → `{order, candidates, dhaeis, stats}` |
| `GET` | `/api/results` | DHAEIs gần nhất |
| `GET` | `/api/dae-lists` | soi toàn bộ DAE-List (cửa sổ + entry + cận âm) |
| `POST` | `/api/reset` · `/api/load-example` | xóa luồng / nạp lại Bảng 1 |
| `GET` | `/api/example-stream` | luồng mẫu gốc |

### 4.2. Kiểm chứng độ đúng

| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/api/validate` | đối chiếu thuật toán với ground truth → `{sound, agreement, missing, extra, speedup}` |
| `POST` | `/api/pruning-comparison` | so sánh cắt tỉa âm vs bản PDF (đánh đổi tốc độ ↔ độ đúng) |

### 4.3. Thực nghiệm

| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/api/bench` | đo 1 cấu hình (thuật toán vs ground truth) |
| `POST` | `/api/scalability` | quét nhiều kích thước luồng |
| `POST` | `/api/sweep` | quét tham số `f`/`minae` trên luồng hiện tại |
| `POST` | `/api/construction-cost` | đo chi phí Pha 1 — kiểm chứng `O(\|T_j\|)` |

### 4.4. Dữ liệu & giải thích

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/datasets` | danh sách bộ dữ liệu dựng sẵn |
| `POST` | `/api/dataset/load` | nạp bộ dữ liệu (`bang1_paper`, `market_200`, `market_1000`) |
| `POST` | `/api/dataset/generate` | sinh luồng tổng hợp (tất định theo `seed`) |
| `POST` | `/api/dataset/import` | nhập CSV `tid,item,qty` (tự suy `eu/inv`) |
| `GET` | `/api/export?fmt=csv\|json` | xuất DHAEIs + luồng |
| `GET` | `/api/explain?pattern=b,c` | truy vết một pattern (số liệu 3 pha + lý do) |
| `GET` | `/api/explain/all` | giải thích toàn bộ kết quả |
| `GET` | `/api/metrics` | chỉ số vận hành (quy mô DAE-List, số entry…) |

### 4.5. Ví dụ nhanh

```bash
# Khai thác theo tham số mặc định của PDF
curl -X POST localhost:8000/api/mine -H "Content-Type: application/json" \
     -d '{"f":0.8,"minae":0.2}'
# -> order [a,b,c], dhaeis [{b},{c},{b,c}]

# Kiểm chứng độ đúng (so với duyệt tất cả tập mục)
curl -X POST localhost:8000/api/validate -H "Content-Type: application/json" \
     -d '{"f":0.8,"minae":0.2}'
# -> {"sound": true, "agreement": 1.0, "missing": [], ...}

# Sinh dữ liệu thực nghiệm 1000 GD / 18 mục rồi khai thác
curl -X POST localhost:8000/api/dataset/generate -H "Content-Type: application/json" \
     -d '{"n_transactions":1000,"n_items":18,"seed":42,"load":true}'
```

---

## 5. Dashboard

`http://localhost:8000/ui` — 6 màn hình, giao diện tối, biểu đồ SVG tự vẽ:

1. **Tổng quan** — KPI, sơ đồ 3 pha, biểu đồ Sdae, kiểm chứng nhanh 1 nút.
2. **Dữ liệu** — chọn/sinh/nhập CSV, bảng `eu/cu/inv`, danh sách giao dịch.
3. **Khai thác** — chạy khai thác (chọn chế độ cắt tỉa), bảng DHAEIs, bảng ứng viên,
   biểu đồ thứ tự ưu tiên.
4. **DAE-List** — soi từng node & entry cấp giao dịch (kèm cận âm).
5. **Thực nghiệm** — benchmark, so sánh 2 chiến lược cắt tỉa, scalability, sweep, chi phí Pha 1.
6. **Giải thích** — truy vết một pattern: đóng góp từng giao dịch + lý do kết luận.

---

## 6. Kết quả thực nghiệm

Số liệu đầy đủ (sinh tự động, tái lập được): [`docs/results/experiments.md`](docs/results/experiments.md).

### 6.1. Độ đúng (luồng tổng hợp, `f=0.8`, `minae=0.2`)

| Luồng | HAEI (thuật toán) | HAEI (ground truth) | Khớp | Thời gian | Ground truth | Nhanh hơn |
|---|---|---|---|---|---|---|
| 100 GD / 6 mục (giỏ ≤ 4) | 4 | 4 | **100%** | 0.007 s | 0.006 s | 0.8× |
| 200 GD / 8 mục (giỏ ≤ 6) | 8 | 8 | **100%** | 0.023 s | 0.023 s | 1.0× |
| 500 GD / 12 mục (giỏ ≤ 8) | 33 | 33 | **100%** | 0.19 s | 0.19 s | 1.0× |
| 1000 GD / 18 mục (giỏ ≤ 12) | 49 | 49 | **100%** | 0.53 s | 4.33 s | **8.2×** |
| 2000 GD / 20 mục (giỏ ≤ 12) | 74 | 74 | **100%** | 1.71 s | 7.93 s | 4.6× |

> Ở luồng nhỏ, chi phí tính cận trên âm có thể ngang hoặc lớn hơn ground truth
> (vì ground truth rất rẻ khi giỏ hàng ngắn). Lợi thế xuất hiện rõ khi giỏ
> hàng dài — đúng đặc tính mũ của ground truth `O(Σ2^|T_j|)`: ở 1000 GD, ground
> truth phải duyệt **797 164** tập mục trong khi thuật toán chỉ thử **~120**
> phép ghép.

### 6.2. Đánh đổi tốc độ ↔ độ đúng

| Luồng | Chiến lược | Thời gian | HAEI tìm được | Khớp ground truth | Bỏ sót |
|---|---|---|---|---|---|
| 500 GD / 14 mục | **âm** (an toàn) | 0.26 s | 39 / 39 | **100%** | — |
| | kiểu PDF | 0.12 s | 39 / 39 | 100% | — |
| 1000 GD / 18 mục | **âm** (an toàn) | 0.57 s | 49 / 49 | **100%** | — |
| | kiểu PDF | 0.35 s | 48 / 49 | 97,96% | `{f,m}` |
| 2000 GD / 20 mục | **âm** (an toàn) | 1.29 s | 43 / 43 | **100%** | — |
| | kiểu PDF | 1.14 s | 43 / 43 | 100% | — |

> Bản "kiểu PDF" **không phải lúc nào cũng sai** — sai ở quy mô đủ lớn. Đó
> chính là lý do cần kiểm chứng tự động bằng ground truth thay vì tin vào
> "cận trên chặt là chặt".

### 6.3. Chi phí Pha 1 — kiểm chứng `O(|T_j|)`

600 giao dịch / 12 mục: thời gian mỗi giao dịch nửa đầu **0.029 ms**, nửa sau
**0.021 ms** → hệ số phình to **0.72** (≈ 1) ⇒ không quét lại dữ liệu cũ.

### 6.4. Độ nhạy tham số (1000 GD / 18 mục)

Số HAEI **tăng** theo `f` (suy giảm nhẹ hơn → tích luỹ nhiều hơn) và **giảm**
theo `minae` (ngưỡng cao hơn → ít tập đạt). Ví dụ `f=0.8`: `minae=0.05` → 495 HAEI,
`minae=0.4` → 13 HAEI.

---

## 7. Kiểm thử

```bash
python -m pytest tests -v      # 93 test
```

| File | Nội dung |
|---|---|
| `test_haeim.py` | khớp PDF: `Sdae`, `SMDAEUB`, thứ tự, cắt tỉa, ghép tiền tố, `LTDAEUB`, cache, bulk, item động |
| `test_ground_truth.py` | **30 luồng ngẫu nhiên**: thuật toán âm khớp 100% ground truth; kiểm tra trực tiếp cận âm ≥ giá trị thật; ground truth không cắt bớt ngữ nghĩa |
| `test_api.py` | 20 test tích hợp cho toàn bộ endpoint (TestClient) |
| `test_datasets_bench.py` | tính tất định của bộ sinh, hiệu chuẩn thang đo, CSV round-trip, benchmark/sweep/scalability, `O(\|T_j\|)` |

---

## 8. Giới hạn & hướng phát triển

**Giới hạn hiện tại**
- Ground truth `O(Σ2^|T_j|)` → chỉ dùng được cho luồng nhỏ/giỏ hàng ngắn
  (đã có chặn an toàn, không cắt bớt ngữ nghĩa).
- Cận trên âm lỏng hơn cận 1-phần-mở-rộng ⇒ tốn thời gian hơn ~1.3–2×.
- Dữ liệu thực nghiệm là dữ liệu **tổng hợp** (đã hỗ trợ nhập CSV để chạy
  trên dữ liệu thật).

**Hướng phát triển** (chi tiết ở `docs/ARCHITECTURE.md` §7): cận âm chặt hơn theo
tỉ lệ hiệu suất (Dinkelbach), chạy nền Restructure/Expansion, xuất báo cáo
LaTeX tự động, nạp dữ liệu thật (UCI Online Retail…).

---

## 9. Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | kiến trúc, cấu trúc dữ liệu, phân tích độ phức tạp, chứng minh tính an toàn |
| [`docs/DEFENSE.md`](docs/DEFENSE.md) | Q&A dự kiến khi bảo vệ luận văn |
| [`docs/results/experiments.md`](docs/results/experiments.md) | toàn bộ số liệu thực nghiệm (sinh tự động) |
| `http://localhost:8000/docs` | Swagger UI |

---

## 10. Ánh xạ PDF → mã nguồn

| PDF (§) | Mã nguồn |
|---|---|
| §1 Luồng `Tj`, `f`, `minae`, `eu/inv` | `app/core/data.py`, `app/schemas.py` |
| §2 Bảng 1, Bảng 2, `f=0.8, Ltid=8, minae=0.2` | `EXAMPLE_STREAM`, `EU/CU/INV`, `DEFAULT_F/MINAE` |
| §3 DAE-List 2 cấp (window + entry) | `DAENode`, `DAEEntry` |
| §3 Lưu ý: Construction lưu **thô**, Restructure mới áp suy giảm | `construction()` vs `restructure()` |
| §4 Pha 1 Construction `O(\|T_j\|)` | `POST /api/transactions` → `construction()` |
| §4 Pha 2 Restructure (lọc, sort, TDAEUB) | `restructure()` |
| §4 Pha 3 Expansion (DFS, ghép tiền tố, LTDAEUB) | `expansion()` + `_join()` (2 con trỏ) |
| §5 Sơ đồ tổng quan | `POST /api/mine` = Restructure + Expansion |
| *(bổ sung)* Cắt tỉa an toàn | `app/core/bounds.py` |
| *(bổ sung)* Ground truth | `app/core/baseline.py` |
