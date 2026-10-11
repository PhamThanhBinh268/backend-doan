# HAEIM_Damped Backend

Backend khai thác **tập mục hiệu suất trung bình cao trên luồng dữ liệu suy giảm (Damped)**,
bám sát tài liệu `TongHop_LuongXuLy_HAEIM_Damped.pdf` (3 pha: **Construction → Restructure → Expansion**,
cấu trúc **DAE-List**, cận trên **MAEUB/MDAEUB/TDAEUB/LTDAEUB**).

## 1. Ánh xạ PDF → Code

| PDF (§) | Backend |
|---|---|
| §1 Input/Output: luồng `Tj=(item,qty)`, `f (0<f<1)`, `minae`, `investmentTable`, `eu` | `app/core/data.py` (`EU/CU/INV`), `app/schemas.py` (`MineRequest`) |
| §2 Bảng 1 + Bảng 2 + tham số `f=0.8, Ltid=8, minae=0.2` | `EXAMPLE_STREAM`, `DEFAULT_F/MINAE`; `miner.load_example_stream()` |
| §3 DAE-List 2 cấp (window `Sdae/Inv/PI/SMDAEUB/STDAEUB` + entry `u/maxru/minInv/PU/dae/MDAEUB/k`) | `app/core/haeim_damped.py`: `DAENode`, `DAEEntry` |
| Lưu ý quan trọng: Construction lưu **thô** `ae/MAEUB`, Restructure mới nhân `f^(Ltid-tid)` | `construction()` chỉ tính `ae/maeub` thô; `restructure()` mới tính `dae/mdaeub` |
| Pha 1 Construction (mỗi `T_j`, `O(\|T_j\|)`, không quét lại) | `POST /api/transactions` → `miner.construction()` |
| Pha 2 Restructure (áp suy giảm, lọc `SMDAEUB<minae`, sort tăng dần, tính `Sdae/TDAEUB/STDAEUB`) | `miner.restructure()` |
| Pha 3 Expansion (DFS: `Sdae>=minae`→kết quả, `STDAEUB>=minae`→ghép, `LTDAEUB` dừng sớm) | `miner.expansion()` + `_join()` (2 con trỏ trên tidList) |
| §5 Sơ đồ tổng quan | `POST /api/mine` = Restructure+Expansion; `GET /api/results` |

### Công thức (đã kiểm chứng bằng code khớp Ví dụ 1–4)

- `eu`: suy từ Bảng 1 (`utility/qty`): `a=4,b=3,c=5,d=2,e=4,f=2`.
- `INV` (Bảng 2, tĩnh): `a=96,b=51,c=72,d=162,e=91,f=50` (=`cu × tổng_qty`).
- `u(X,Tj)=Σ qty·eu`, `Inv(X)=Σ INV`, **`ae(X,Tj)=u/(Inv·|X|)`** (Công thức 5 — trung bình).
  Kiểm chứng: `ae({a},T1)=4/96/1=0.0417` (Ví dụ 1); `Sdae` singleton với
  `f=0.8,Ltid=8`: `{a}=0.188,{b}=0.541,{c}=0.598` khớp PDF (sai số <0.005).
- `dae=ae·f^(Ltid-tid)`, `Sdae=Σdae`.
- `MAEUB`: greedy giảm dần tiện ích, chỉ xét mục **sau** X (remaining-utility),
  lấy max **hiệu suất** `u/Inv` (không chia len — chặn trên lỏng, an toàn).
  Nhờ đó `MAEUB({a},T1)=0.0417` (c đứng trước a nên không xét `{a,c}`).
- `MDAEUB=MAEUB·w`, `SMDAEUB=ΣMDAEUB` (lọc Restructure; giữ `a,b,c`, loại `d,e,f`).
- `TDAEUB` (3 trường hợp): `k==0→0` (vd `{c}` cuối → `STDAEUB=0`); else
  `(u+maxru)/((Inv+minInv)·(|X|+1))·w` (= ae của 1-extension tốt nhất).
  → `STDAEUB(a)~0.17<0.2` cắt, `STDAEUB(b)~0.28≥0.2` mở rộng, `STDAEUB(c)=0`.
  Chỉ `{b}×{c}` được ghép (Ví dụ 5).
- Ghép `Pxy`: `u=u_x+u_y−PU`, `Inv=Inv_x+Inv_y−PI`, `LTDAEUB` khởi tạo `STDAEUB(Px)`
  trừ dần tid lệch để dừng sớm.

### Hiệu chỉnh trung thực (do ảnh công thức trong PDF bị mất chữ)

1. `Sdae({b,c})`: code cho `0.2829`, PDF ghi `0.2047`. Cả hai đều `>0.2` nên cùng
   kết luận **HAEI**, tập `DHAEIs={b,c,{b,c}}` **giống hệt PDF**. Chênh lệch do
   Công thức 5/PI chi tiết cho itemset dài nằm trong ảnh mất chữ; code dùng định
   nghĩa average chuẩn `u/(Inv·|X|)` và đã ghi rõ.
2. `SMDAEUB(a)`: code `0.2245`, PDF `0.206` (chênh `0.018`). Do điều kiện dừng greedy
   của MAEUB trong PDF ("mục kế tiếp có … → dừng") bị mất chữ; code lấy max trên
   toàn bộ remaining (chặn trên lỏng nhưng **an toàn** — không bỏ sót HAEI, vẫn lọc
   đúng `a,b,c`).
3. `TDAEUB` 3-case: PDF chỉ nêu tên, code cài đặt bound chặt cho average-efficiency
   như trên và tái hiện đúng hành vi cắt tỉa (chỉ `{b}` mở rộng).

## 2. Chạy

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

## 3. API

- `GET /` — trạng thái, `ltid`, số giao dịch.
- `GET /api/config` — `eu/cu/inv`, `f/minae` mặc định.
- `GET /api/transactions` / `POST /api/transactions {tid?, items:[{item,qty}]}` — Pha 1.
- `POST /api/items {item, eu, inv}` — đăng ký mục mới phát sinh trên luồng (ngoài a..f).
- `POST /api/mine {f, minae}` — Pha 2+3, trả `{order, candidates, dhaeis}`.
- `GET /api/results` — DHAEIs gần nhất.
- `GET /api/dae-lists` — soi toàn bộ DAE-List (window + entries).
- `POST /api/load-example` — nạp lại Bảng 1 (8 GD). `POST /api/reset` — xóa luồng.
- `GET /api/example-stream` — luồng mẫu gốc.

> Cập nhật theo PDF: `_join` chỉ ghép cùng tiền tố + `LTDAEUB` dừng sớm
> (`STDAEUB(Px)` trừ dần tid lệch, kiểm tra cả sau vòng lặp);
> `SMDAEUB` của pattern dài = Σ hiệu suất suy giảm (vd `{b,c}: smdaeub=0.5658 >= sdae=0.2829`);
> `MAEUB` có điều kiện dừng sớm an toàn không đổi kết quả;
> `miner` thread-safe (`RLock`), validate `f/minae/qty`, hỗ trợ item động.

Ví dụ:

```bash
curl -X POST localhost:8000/api/mine -H "Content-Type: application/json" -d "{\"f\":0.8,\"minae\":0.2}"
# -> order [a,b,c], dhaeis [{b},{c},{b,c}]
curl -X POST localhost:8000/api/transactions -H "Content-Type: application/json" -d "{\"items\":[{\"item\":\"a\",\"qty\":1},{\"item\":\"b\",\"qty\":2}]}"
```

## 4. Test

```bash
python -m pytest tests -v
# 7 tests: Sdae khớp PDF, SMDAEUB khớp PDF (±0.02), pruning + DHAEIs,
# streaming không quét lại, join tiền tố + LTDAEUB, Sdae({b,c}) HAEI, item động + validate.
```
