"""Kiểm chứng ĐỘ ĐÚNG của thuật toán cắt tỉa (so với ground truth).

Nguyên tắc: phép cắt tỉa trong HAEIM_Damped chỉ được chấp nhận khi **không bỏ
sót HAEI nào** (`sound`) và **không sinh thừa** (`complete`). Ground truth ở đây
là `app/core/baseline.py::exact_mine` — duyệt TẤT CẢ tập mục con của mọi giao
dịch, hoàn toàn không dùng cắt tỉa.

Các test này là "lưới an toàn" cho mọi thay đổi sau này: nếu ai đó tối ưu
(thay đổi công thức, đổi điều kiện dừng sớm, đổi bộ lọc) mà làm hỏng tính
đúng thì test sẽ đỏ.
"""
from __future__ import annotations

import pytest

from app.core.baseline import canonical, compare_with_exact, exact_mine
from app.core.datasets import generate_stream, parse_csv, stream_to_csv
from app.core.haeim_damped import HAEIMDampedMiner


def _miner_from(ds) -> HAEIMDampedMiner:
    m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu)
    m.bulk_construction(
        [(tid, sorted(t.items())) for tid, t in sorted(ds.transactions.items())]
    )
    return m


# --------------------------------------------------------------------------
# 1. ÂM TÍNH: không bỏ sót HAEI, không sinh thừa
# --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 7, 11, 13])
def test_pruning_is_sound_and_complete(seed):
    """Mọi tập HAEI phải khớp 100% với duyệt tất cả tập mục."""
    ds = generate_stream(30, 6, seed=seed, min_items_per_tx=2, max_items_per_tx=4)
    m = _miner_from(ds)
    for minae in (0.05, 0.1, 0.2, 0.3):
        out = m.mine(f=0.8, minae=minae)
        truth = exact_mine(ds.transactions, ds.eu, ds.inv_table, 0.8, minae)
        cmp = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)
        assert cmp["sound"], f"bỏ sót HAEI (seed={seed}, minae={minae}): {cmp['missing']}"
        assert cmp["complete"], f"sinh thừa (seed={seed}, minae={minae}): {cmp['extra']}"
        assert cmp["agreement"] == 1.0


def test_singleton_superset_not_lost():
    """Regression: bộ lọc Pha 2 (SMDAEUB) từng loại mục làm mất tập mục chứa nó.

    Trước đây `d` bị lọc ở Restructure vì SMDAEUB(d) < minae, khiến tập mục
    {d,f} (là HAEI) không bao giờ được sinh ra.
    """
    ds = generate_stream(40, 6, seed=2, min_items_per_tx=2, max_items_per_tx=4)
    m = _miner_from(ds)
    out = m.mine(f=0.8, minae=0.1)
    truth = exact_mine(ds.transactions, ds.eu, ds.inv_table, 0.8, 0.1)
    assert canonical(("d", "f")) in truth.patterns          # ground truth có
    assert canonical(("d", "f")) in {canonical(d["pattern"]) for d in out["dhaeis"]}


def test_paper_stream_matches_exact():
    """Bảng 1 của PDF: kết quả cắt tỉa phải khớp ground truth."""
    from app.core.data import EU, EXAMPLE_STREAM, INV

    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.bulk_construction(
        [(tid, [(i, q) for i, q in EXAMPLE_STREAM[tid]]) for tid in sorted(EXAMPLE_STREAM)]
    )
    for minae in (0.1, 0.2, 0.3, 0.5):
        out = m.mine(f=0.8, minae=minae)
        truth = exact_mine(m.transactions, m.eu, m.inv_table, 0.8, minae)
        cmp = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)
        assert cmp["sound"] and cmp["complete"], cmp


# --------------------------------------------------------------------------
# 2. Tính đúng của công thức (đối chiếu định nghĩa, không qua implementation)
# --------------------------------------------------------------------------
def test_sdae_formula_independent_recomputation():
    """Tự tính lại Sdae theo Công thức 5 rồi so với kết quả của miner."""
    ds = generate_stream(25, 5, seed=99)
    m = _miner_from(ds)
    out = m.mine(f=0.8, minae=0.0)
    ltid = max(ds.transactions)

    def sdae_manual(pat):
        s = 0.0
        for tid, tmap in ds.transactions.items():
            if all(i in tmap for i in pat):
                u = sum(tmap[i] * ds.eu[i] for i in pat)
                inv = sum(ds.inv_table[i] for i in pat)
                s += u / (inv * len(pat)) * (0.8 ** (ltid - tid))
        return s

    for r in out["dhaeis"]:
        assert r["sdae"] == pytest.approx(sdae_manual(tuple(r["pattern"])), abs=1e-3)


# --------------------------------------------------------------------------
# 3. Module dữ liệu & CSV
# --------------------------------------------------------------------------
def test_generate_stream_is_deterministic():
    a = generate_stream(20, 6, seed=5)
    b = generate_stream(20, 6, seed=5)
    assert a.transactions == b.transactions
    assert a.eu == b.eu and a.inv_table == b.inv_table
    c = generate_stream(20, 6, seed=6)
    assert c.transactions != a.transactions


def test_csv_roundtrip():
    ds = generate_stream(15, 5, seed=3)
    csv = stream_to_csv(ds.transactions)
    back = parse_csv(csv)
    assert set(back) == set(ds.transactions)
    for tid, tmap in ds.transactions.items():
        assert back[tid] == pytest.approx(tmap)


def test_parse_csv_rejects_bad_rows():
    with pytest.raises(ValueError):
        parse_csv("1,a\n")              # thiếu cột qty
    with pytest.raises(ValueError):
        parse_csv("1,a,0\n")            # qty <= 0
    with pytest.raises(ValueError):
        parse_csv("")                   # rỗng


# --------------------------------------------------------------------------
# 4. API: lỗi đầu vào phải trả 400 (không phải 500)
# --------------------------------------------------------------------------
@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_import_csv_partial_inv_returns_400(client):
    r = client.post("/api/dataset/import", json={
        "csv": "1,a,2\n2,b,1\n",
        "inv": {"a": 10},
        "load": True,
    })
    assert r.status_code == 400, r.text


def test_import_csv_partial_eu_returns_400(client):
    r = client.post("/api/dataset/import", json={
        "csv": "1,a,2\n2,b,1\n",
        "eu": {"a": 1.0},
        "load": True,
    })
    assert r.status_code == 400, r.text


def test_explain_matches_dae_list(client):
    """Số liệu giải thích phải khớp đúng bảng DAE-List của thuật toán."""
    client.post("/api/reset", json={})
    client.post("/api/load-example", json={})
    mine = client.post("/api/mine", json={"f": 0.8, "minae": 0.2}).json()
    cand = {tuple(c["pattern"])[0]: c for c in mine["candidates"]}

    for item, c in cand.items():
        ex = client.get(f"/api/explain?pattern={item}").json()
        assert ex["smdaeub"] == pytest.approx(c["smdaeub"], abs=1e-3), item
        assert ex["stdaeub"] == pytest.approx(c["stdaeub"], abs=1e-3), item
        assert ex["sdae"] == pytest.approx(c["sdae"], abs=1e-3), item


def test_explain_before_mine_has_stdaeub(client):
    """Gọi /api/explain khi CHƯA mine vẫn phải có STDAEUB đúng (không phải 0)."""
    client.post("/api/reset", json={})
    client.post("/api/load-example", json={})
    ex = client.get("/api/explain?pattern=a").json()
    assert ex["stdaeub"] > 0.0
    assert ex["smdaeub"] > 0.0
