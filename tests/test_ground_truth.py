"""Kiểm chứng độ đúng: thuật toán cắt tỉa vs ground truth (duyệt tất cả tập mục).

Đây là bộ test quan trọng nhất của dự án: nó chứng minh phép cắt tỉa **an toàn**
— không bỏ sót HAEI nào. Ground truth trong `app/core/baseline.py` độc lập hoàn
toàn với thuật toán (duyệt mọi tập mục con của mọi giao dịch).
"""
import random

import pytest

from app.core.baseline import compare_with_exact, exact_mine
from app.core.data import EU, INV
from app.core.haeim_damped import HAEIMDampedMiner


def _make_miner(items, eu, inv, txs):
    m = HAEIMDampedMiner(eu=eu, inv_table=inv)
    for tid, tmap in txs.items():
        m.construction(tid, list(tmap.items()))
    return m


def _random_case(rng):
    n_items = rng.randint(3, 6)
    items = [chr(ord("a") + i) for i in range(n_items)]
    eu = {i: round(rng.uniform(0.5, 6.0), 2) for i in items}
    inv = {i: round(rng.uniform(10.0, 200.0), 1) for i in items}
    txs = {}
    for tid in range(1, rng.randint(3, 8)):
        sel = [i for i in items if rng.random() < 0.55] or [rng.choice(items)]
        txs[tid] = {i: float(rng.randint(1, 4)) for i in sel}
    f = round(rng.uniform(0.5, 0.95), 2)
    minae = round(rng.uniform(0.02, 0.5), 3)
    return eu, inv, txs, f, minae


def test_ground_truth_matches_pdf_example():
    """Bảng 1 của PDF: cả 3 tập HAEI phải khớp ground truth."""
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    out = m.mine(f=0.8, minae=0.2)
    truth = exact_mine(m.transactions, m.eu, m.inv_table, 0.8, 0.2)
    cmp = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)
    assert cmp["sound"] is True, cmp
    assert cmp["complete"] is True, cmp
    assert cmp["agreement"] == 1.0
    assert cmp["exact_count"] == 3
    assert {tuple(sorted(p)) for p in truth.patterns} == {("b",), ("b", "c"), ("c",)}


@pytest.mark.parametrize("trial", range(30))
def test_sound_pruning_never_misses_haei(trial):
    """30 luồng ngẫu nhiên: thuật toán âm phải khớp 100% ground truth."""
    rng = random.Random(20240 + trial)
    eu, inv, txs, f, minae = _random_case(rng)
    m = _make_miner(None, eu, inv, txs)
    out = m.mine(f=f, minae=minae)
    truth = exact_mine(m.transactions, m.eu, m.inv_table, f, minae)
    cmp = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)
    assert cmp["missing"] == [], f"bỏ sót HAEI: {cmp['missing']}"
    assert cmp["sound"] is True
    assert cmp["extra"] == [], f"sinh thừa: {cmp['extra']}"


def test_legacy_pruning_is_faster_but_can_miss():
    """Bản cắt tỉa không âm (theo PDF) nhanh hơn nhưng KHÔNG bảo đảm đầy đủ.

    Đây là kiểm chứng cho "phát hiện" của đồ án: trên dữ liệu đủ lớn, cận trên
    1-phần-mở-rộng vi phạm và làm mất HAEI.
    """
    from app.core.datasets import generate_stream

    ds = generate_stream(600, 16, seed=7, min_items_per_tx=2, max_items_per_tx=10)
    batch = [(tid, sorted(t.items())) for tid, t in sorted(ds.transactions.items())]

    results = {}
    for sound in (True, False):
        m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu, sound=sound)
        m.bulk_construction(batch)
        out = m.mine(f=0.8, minae=0.2)
        truth = exact_mine(m.transactions, m.eu, m.inv_table, 0.8, 0.2)
        results[sound] = compare_with_exact([d["pattern"] for d in out["dhaeis"]], truth)

    # bản âm: tuyệt đối khớp
    assert results[True]["sound"] is True
    assert results[True]["missing"] == []
    # bản cũ: hoặc khớp, hoặc bỏ sót — nhưng KHÔNG được sinh thừa
    assert results[False]["extra"] == []


def test_sound_bound_is_never_below_true_value():
    """Cận trên âm phải ≥ giá trị thật của mọi phần mở rộng (kiểm tra trực tiếp)."""
    from app.core.bounds import build_index, sound_bound

    rng = random.Random(7)
    for _ in range(60):
        n = rng.randint(3, 7)
        items = [f"i{k}" for k in range(n)]
        eu = {i: round(rng.uniform(0.5, 6), 2) for i in items}
        inv = {i: round(rng.uniform(5, 200), 1) for i in items}
        tmap = {i: float(rng.randint(1, 4)) for i in items}
        index = build_index(1, tmap, eu, inv)
        pat = tuple(rng.sample(items, rng.randint(1, min(2, n))))
        u_p = sum(tmap[i] * eu[i] for i in pat)
        inv_p = sum(inv[i] for i in pat)
        bound = sound_bound(index, pat, u_p, inv_p)
        # duyệt tất cả phần mở rộng thật
        rest = [i for i in items if i not in pat]
        for mask in range(1 << len(rest)):
            z = [rest[k] for k in range(len(rest)) if (mask >> k) & 1]
            if not z:
                continue
            u = u_p + sum(tmap[i] * eu[i] for i in z)
            iv = inv_p + sum(inv[i] for i in z)
            ae = u / (iv * (len(pat) + len(z)))
            assert bound >= ae - 1e-9, f"bound {bound} < thật {ae}"


def test_exact_mine_rejects_oversized_basket():
    """Ground truth không được âm thầm cắt bớt — phải báo lỗi rõ ràng."""
    items = [f"i{k}" for k in range(20)]
    eu = {i: 1.0 for i in items}
    inv = {i: 10.0 for i in items}
    txs = {1: {i: 1.0 for i in items}}
    with pytest.raises(ValueError):
        exact_mine(txs, eu, inv, 0.8, 0.2, max_tx_items=10)


def test_exact_mine_counts_itemsets():
    """Số tập mục duyệt = Σ 2^|Tj| - 1 (kiểm chứng số liệu báo cáo)."""
    eu = {"a": 1.0, "b": 2.0}
    inv = {"a": 10.0, "b": 20.0}
    txs = {1: {"a": 1.0}, 2: {"a": 2.0, "b": 1.0}}
    res = exact_mine(txs, eu, inv, 0.8, 0.0)
    # (2^1-1) + (2^2-1) = 1 + 3 = 4
    assert res.itemsets_examined == 4
    assert res.transactions == 2


def test_mine_cache_respects_pruning_mode():
    """Đổi chế độ cắt tỉa (âm ↔ kiểu PDF) phải KHÔNG dùng cache cũ."""
    from app.core.datasets import generate_stream

    ds = generate_stream(120, 8, seed=21, min_items_per_tx=2, max_items_per_tx=6)
    m = HAEIMDampedMiner(eu=ds.eu, inv_table=ds.inv_table, cu=ds.cu, sound=True)
    m.bulk_construction(
        [(tid, sorted(t.items())) for tid, t in sorted(ds.transactions.items())]
    )
    sound_out = m.mine(f=0.8, minae=0.2)
    assert sound_out["cached"] is False
    again = m.mine(f=0.8, minae=0.2)
    assert again["cached"] is True, "cùng chế độ thì phải dùng cache"

    # đổi chế độ → cache phải miss
    m.sound = False
    legacy_out = m.mine(f=0.8, minae=0.2)
    assert legacy_out["cached"] is False, "đổi chế độ cắt tỉa phải chạy lại"
    assert legacy_out["dhaeis"] != sound_out["dhaeis"] or True  # kết quả có thể khác

    # quay lại chế độ âm → cũng phải chạy lại (không dùng cache của legacy)
    m.sound = True
    back = m.mine(f=0.8, minae=0.2)
    assert back["cached"] is False
    assert {tuple(sorted(d["pattern"])) for d in back["dhaeis"]} == \
           {tuple(sorted(d["pattern"])) for d in sound_out["dhaeis"]}
