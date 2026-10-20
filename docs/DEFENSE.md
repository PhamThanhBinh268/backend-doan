# Q&A dự kiến khi bảo vệ luận văn

> Tài liệu tự chuẩn bị: các câu hỏi hội đồng thường hỏi kèm **trả lời ngắn gọn,
> có số liệu** và **chỗ dẫn tham chiếu** trong mã nguồn. Mọi con số đều tái lập
> được bằng `python scripts/run_experiments.py`.

---

## A. Về bài toán & mô hình

**Hỏi: HAEIM khác HUI ở chỗ nào?**
Đây là bài toán *High Average Efficiency Itemset Mining* trên **luồng dữ liệu
suy giảm** (damped). Khác HUI ở hai điểm:
1. Độ đo là **hiệu suất trung bình** `u/(Inv·|X|)` thay vì tần suất → phải chia
   cho `|X|` (Công thức 5), nên tập lớn bị trừ điểm.
2. Luồng có **suy giảm theo thời gian** → mọi đại lượng phải nhân trọng số
   `f^(Ltid−tid)`, và trọng số này thay đổi liên tục ⇒ **Construction chỉ lưu
   giá trị thô**, suy giảm áp tại Restructure.

**Hỏi: Vì sao `Inv(X)` không nhân với số lượng?**
Vì `Inv` là **chi phí đầu tư tĩnh** của mục (Bảng 2 của PDF). Kiểm chứng:
`ae({a},T1) = 4/96/1 = 0.0417` — khớp 100% Ví dụ 1. Nếu nhân qty thì kết quả
sai ngay.

**Hỏi: `Ltid` là gì?**
Largest Transaction ID — mã của giao dịch lớn nhất trong luồng. Dùng làm mốc
cho trọng số suy giảm: giao dịch càng xa thời điểm hiện tại càng bị giảm giá.

**Hỏi: Tại sao khai thác lại cần chạy định kỳ (Restructure + Expansion) mà
không khai thác ngay khi có giao dịch mới?**
Vì trọng số `f^(Ltid−tid)` phụ thuộc `Ltid` — cứ mỗi giao dịch mới là mọi
đại lượng cũ biến đổi. Nếu khai thác ngay, mỗi lần phải tính lại toàn bộ
DAE-List (`O(N)`), tức `O(N²)` cho cả luồng. Mô hình 3 pha giữ **Pha 1 rẻ
(`O(|T_j|)`)** và gom việc nặng về chu kỳ.

---

## B. Về thuật toán & độ phức tạp

**Hỏi: Pha 1 có thực sự O(|T_j|)?**
Có. `_construct_locked` chỉ ghi entry cho các mục trong `T_j` và tính MAEUB
thô bằng greedy trên thứ tự **đã sort sẵn** 1 lần/GD — không đọc lại
`self.transactions` hay `self.nodes` cũ.
*Kiểm chứng:* đo 600 GD/12 mục → thời gian/GD nửa đầu 0.029 ms, nửa sau
0.021 ms, **hệ số phình to 0.72 ≈ 1** (`POST /api/construction-cost`).

**Hỏi: Vì sao ghép 2 tập mục dùng 2 con trỏ?**
Vì `tidList` của 2 node đã được sort theo `tid` tại Restructure → thuật toán
2 con trỏ tìm các `tid` chung **và** trừ dần `LTDAEUB` trong **1 pass duy
nhất**, `O(n+m)`, không tạo dict/set trung gian. Kết quả giống hệt bản
"merge rồi tra set" nhưng nhanh hơn và giữ nguyên tính chất streaming.

**Hỏi: Tại sao chỉ ghép 2 node *cùng tiền tố*?**
Để **không sinh trùng**: mọi tập mục k-itemset có đúng một tiền tố (k−1)-itemset
theo thứ tự, nên mỗi tập được sinh đúng 1 lần (như Apriori). Với singleton,
tiền tố rỗng → mọi cặp đều hợp lệ (đúng Ví dụ 5: `{b}×{c}` → `{b,c}`).

**Hỏi: `LTDAEUB` dùng để làm gì?**
Dừng sớm phép ghép: `LTDAEUB` là cận trên của `Sdae` tập mục kết quả. Nếu
`< minae` thì tập kết quả chắc chắn không phải HAEI → bỏ qua phép ghép, tiết
kiệm thời gian.

---

## C. Về cắt tỉa & độ đúng (phần quan trọng nhất)

**Hỏi: Làm sao chứng minh thuật toán không bỏ sót HAEI?**
Đây là điểm **phát hiện quan trọng** của đồ án:

1. Xây **ground truth độc lập** (`app/core/baseline.py`): duyệt *mọi* tập mục
   con của *mọi* giao dịch — không dùng bất kỳ cắt tỉa nào → có "đáp án đúng".
2. So sánh tự động: `POST /api/validate` + `tests/test_ground_truth.py`
   (30 luồng ngẫu nhiên, seed cố định).
3. Kết quả: bản cắt tỉa kiểu bài báo **bỏ sót** HAEI ở quy mô lớn
   (1000 GD/18 mục: thiếu `{f,m}`, khớp 97,96%).

**Hỏi: Vì sao bản bài báo lại bỏ sót?**
Công thức cận trên kiểu bài báo
`TDAEUB = (u(X)+maxru)/((Inv(X)+minInv)·(|X|+1))·w`
chỉ chặn trên **đúng** với phần mở rộng **thêm 1 mục**. Với phần mở rộng thêm
`m ≥ 2` mục, tổng tiện ích có thể vượt `u(X)+maxru` (vì `maxru` chỉ là tiện
ích **đơn** lớn nhất) → **cận trên vi phạm** → nhánh bị cắt oan → mất HAEI.

**Hỏi: Đồ án đã sửa thế nào?**
Thay bằng **cận trên âm** (`app/core/bounds.py`):
```
B(X,Tj) = max_{m=1..|R|} (u(X)+U_max(m)) / ((Inv(X)+I_min(m))·(|X|+m))
```
với `U_max(m)` = tổng tiện ích `m` mục lớn nhất còn lại, `I_min(m)` = tổng chi
phí `m` mục rẻ nhất còn lại. Vì `u(X∪Z) ≤ u(X)+U_max(m)` và
`Inv(X∪Z) ≥ Inv(X)+I_min(m)` nên `B` **luôn ≥ giá trị thật** ⇒
`Sdae(Y) ≤ sbound(X)` cho mọi `Y ⊇ X` ⇒ cắt tỉa **an toàn tuyệt đối**.
Kết quả: **khớp 100% ground truth** ở mọi cấu hình đã thử.

**Hỏi: Tốn thêm bao nhiêu?**
Khoảng **1.3–2×** so với bản cũ (bản cũ sai). Đổi lại: tìm đủ 49/49 HAEI
thay vì 48/49, và nhanh hơn ground truth **10.5×** ở luồng 1000 GD (ground
truth phải duyệt 797 164 tập mục).

**Hỏi: Có làm chậm quá không?**
Không, vì:
- Chỉ giỏ hàng ≤ 6 mục mới duyệt tập mục con **chính xác** (2^|R| ≤ 64);
  giỏ hàng lớn dùng cận lỏng (vẫn âm) — tham số `EXACT_SUBSET_LIMIT`, đo tối
  ưu trong `bounds.py`.
- Cận "kiểu PDF" chỉ dùng để **hiển thị** nên đã tách khỏi đường ghép nóng
  (tăng tốc ~1.9× cho Pha 3).

**Hỏi: Ground truth có bị "cắt bớt" không?**
Không — nếu giao dịch có quá nhiều mục, hàm **ném lỗi** chứ không âm thầm
bỏ qua (`exact_mine` raise `ValueError`). Test `test_exact_mine_rejects_oversized_basket`
kiểm chứng điều này.

---

## D. Về thực nghiệm & số liệu

**Hỏi: Số liệu trong báo cáo lấy ở đâu?**
Chạy `python scripts/run_experiments.py` → ghi ra `docs/results/experiments.{json,md}`.
Toàn bộ **tất định theo seed** → chạy lại cho kết quả y hệt.

**Hỏi: Dữ liệu thực nghiệm là dữ liệu thật hay tổng hợp?**
Tổng hợp, mô phỏng dữ liệu siêu thị: phổ biến theo **Zipf**, số lượng ngẫu
nhiên 1..5, **trôi thị phần theo thời gian** (random walk log có hồi phục —
để hệ số suy giảm có ý nghĩa). Ngoài ra hệ thống hỗ trợ **nhập CSV** để chạy
trên dữ liệu thật (`POST /api/dataset/import`).
*Điểm hiệu chuẩn:* để ngưỡng `minae=0.2` (đặt cho thang đo của PDF) có ý
nghĩa, bộ sinh **co giãn INV** để đưa Sdae trung vị của singleton về vùng làm
việc — không thay đổi thứ tự so sánh giữa các mục.

**Hỏi: Vì sao ở luồng nhỏ, thuật toán không nhanh hơn ground truth?**
Vì ground truth `O(Σ2^|T_j|)` rất rẻ khi giỏ hàng ngắn (2^4 = 16 tập mục/giao
dịch), trong khi thuật toán phải trả chi phí cố định cho việc tính cận trên âm
ở mọi entry. Lợi thế xuất hiện khi giỏ hàng dài — đúng đặc tính mũ. Bảng
số liệu §6.1 của README thể hiện rõ điều này (0.7× → **10.5×**).

**Hỏi: Số lượng HAEI phụ thuộc tham số thế nào?**
- Tăng `f` (suy giảm nhẹ hơn) → giao dịch cũ giữ giá trị hơn → **nhiều** HAEI
  hơn (f=0.8: 495 HAEI ở `minae=0.05`).
- Tăng `minae` (ngưỡng cao hơn) → **ít** HAEI hơn (cùng f=0.8: 13 HAEI ở
  `minae=0.4`).

**Hỏi: Vì sao `{a}` không phải HAEI trong ví dụ PDF?**
`Sdae({a}) = 0.188 < minae = 0.2` → không đạt ngưỡng, dù `SMDAEUB({a}) ≈ 0.224`
(cận trên) vượt ngưỡng. Đây là ví dụ điển hình cho việc cần phân biệt **giá trị
thật** và **cận trên**.

---

## E. Về kỹ thuật & hiện thực

**Hỏi: Vì sao dùng FastAPI + không có frontend framework?**
Yêu cầu "cài đặt 1 lệnh, không lo xung đột môi trường" khi bảo vệ. Toàn bộ
dashboard là Vanilla JS + biểu đồ SVG tự vẽ → không cần Node, không cần build
step, không có rủi ro cài đặt. Backend chỉ dùng 5 thư viện phổ biến.

**Hỏi: Có xử lý đồng thời không?**
Có: `HAEIMDampedMiner` dùng `threading.RLock` cho mọi thao tác trên trạng
thái; `mine()` có **cache** theo `(f, minae, ltid, số GD, version)` nên poll UI
liên tục không chạy lại vô ích (trả `cached: true`).

**Hỏi: Có hỗ trợ dữ liệu thay đổi giữa chừng không?**
Có. `construction()` chỉ bổ sung entry mới, không quét lại → phù hợp luồng.
`register_item()` cho mục mới xuất hiện; `load_dataset()` nạp bộ dữ liệu mới
(atomic: validate trước, lỗi thì giữ nguyên trạng thái cũ).

**Hỏi: Làm sao biết thuật toán "đúng" khi trình bày?**
Mở tab **Thực nghiệm** → **Kiểm chứng** (1 nút) hoặc gọi `POST /api/validate`:
trả về `sound: true`, `agreement: 1.0`, `missing: []` — tức thuật toán khớp
100% với ground truth trên chính luồng đang hiển thị.

---

## F. Câu hỏi "khó" dự kiến

**Hỏi: Cận trên âm của anh có thực sự cần thiết, hay chỉ là do lỗi lập trình?**
Không phải lỗi lập trình — là **hạn chế của công thức**. Công thức
`(u+maxru)/((Inv+minInv)·(|X|+1))` là cận trên **chính xác** cho phần mở rộng
thêm đúng 1 mục. Khi phần mở rộng thêm ≥ 2 mục, tổng tiện ích có thể vượt
`u+maxru` ⇒ công thức **không còn là cận trên**. Cần một cận trên khác — và
cận trên âm là lựa chọn đơn giản nhất vẫn đảm bảo tính đúng.

**Hỏi: Có thể dùng cận trên chặt hơn mà vẫn âm không?**
Có — đây là hướng mở rộng đã ghi trong `docs/ARCHITECTURE.md` §7: thay cặp
`U_max`/`I_min` (độc lập, gây lỏng) bằng ràng buộc tỉ lệ hiệu suất kiểu
Dinkelbach, tức tối ưu `max_{|Z|=m} (u_P+U_Z)/(Inv_P+I_Z)` chính xác thay vì
lấn quanh. Đánh đổi: thêm thời gian tính cận, giảm số nhánh phải mở rộng.

**Hỏi: Nếu ground truth chính là bài toán, sao dùng nó để kiểm chứng được?**
Vì ground truth ở đây là **công cụ kiểm chứng**, không phải giải pháp: nó
chỉ chạy được cho luồng nhỏ (`O(Σ2^|T_j|)`), và nó **không** dùng bất kỳ cắt
tỉa nào nên độc lập với thuật toán đang kiểm chứng. Vai trò của nó là "đáp án
đúng" để đo tỉ lệ khớp.

**Hỏi: Hạn chế lớn nhất của đồ án?**
1. Số liệu thực nghiệm chủ yếu trên dữ liệu **tổng hợp** (đã hỗ trợ CSV để
   chạy dữ liệu thật, nhưng chưa tích hợp bộ dữ liệu công khai).
2. Ground truth chỉ dùng được cho luồng nhỏ → chưa kiểm chứng được trên quy mô
   hàng chục nghìn giao dịch.
3. Restructure/Expansion chạy đồng bộ — có thể song song hoá để khai thác
   liên tục trên luồng dài.

**Hỏi: Nếu hội đồng hỏi "ứng dụng thực tế của đề tài là gì"?**
Khai thác tập mục hiệu suất cao trên luồng giao dịch — ví dụ:
- **Chăm sóc khách hàng**: giỏ hàng chứa nhóm sản phẩm có hiệu suất cao
  (giá trị đơn vị trên vốn) → đề xuất gói/bundle, chiến lược giảm giá theo cụm.
- **Phát hiện gian lận**: tập mục "hợp lý" theo hiệu suất, đặc biệt trên luồng
  giao dịch dài có trôi hành vi.
- **Quản trị tồn kho**: tập mục sinh lời tốt để quyết định đặt hàng/đóng gói.
Vì có yếu tố **suy giảm theo thời gian**, kết quả phản ánh hành vi **hiện tại**
chứ không phải toàn bộ lịch sử — đây chính là giá trị của mô hình damped.

---

## G. Lệnh demo nhanh khi bảo vệ

```bash
# 1) Khởi động
uvicorn app.main:app --port 8000

# 2) Mở dashboard: http://localhost:8000/ui
#    - Tab "Tổng quan": bấm "Kiểm chứng" → sound=true, agreement=100%
#    - Tab "Khai thác": bỏ tick "cắt tỉa âm" → chạy → thấy kết quả bớt HAEI

# 3) Tab "Thực nghiệm": bấm "Chạy so sánh" → thấy bản PDF bỏ sót {f,m}

# 4) Tab "Giải thích": nhập pattern "b,c" → xem truy vết đầy đủ

# 5) Chứng minh với hội đồng (nếu cần):
python -m pytest tests -q                                  # 93 test
python scripts/run_experiments.py --quick                  # tái lập số liệu
curl -X POST localhost:8000/api/validate -H "Content-Type: application/json" \
     -d '{"f":0.8,"minae":0.2}'
```
