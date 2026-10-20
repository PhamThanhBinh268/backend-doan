"""Kiểm thử bộ sinh dữ liệu, CSV I/O và các công cụ đo đạc."""
import pytest

from app.core.bench import (
    clone_miner,
    measure_construction_cost,
    run_benchmark,
    run_pruning_comparison,
    run_scalability,
    run_sweep,
)
from app.core.datasets import (
    generate_stream,
    list_datasets,
    load_dataset,
    parse_csv,
    stream_to_csv,
)
from app.core.haeim_damped import HAEIMDampedMiner


# ------------------------------------------------------------------ datasets
def test_generate_is_deterministic():
    a = generate_stream(50, 8, seed=11)
    b = generate_stream(50, 8, seed=11)
    c = generate_stream(50, 8, seed=12)
    assert a.transactions == b.transactions
    assert a.eu == b.eu
    assert a.inv_table == b.inv_table
    assert a.transactions != c.transactions


def test_generate_shapes_and_ranges():
    ds = generate_stream(120, 10, seed=3, min_items_per_tx=2, max_items_per_tx=5)
    assert ds.n_transactions == 120
    assert ds.n_items == 10
    assert len(ds.transactions) == 120
    for tmap in ds.transactions.values():
        assert 2 <= len(tmap) <= 5
        assert all(q > 0 for q in tmap.values())
    # Inv(i) = cu(i) * tổng_qty(i) * hệ số hiệu chuẩn — cùng quy ước Bảng 2 PDF
    for nm in ds.eu:
        qty = sum(t.get(nm, 0.0) for t in ds.transactions.values())
        assert ds.inv_table[nm] == pytest.approx(
            ds.cu[nm] * qty * ds.calibration_factor, rel=1e-3)


def test_calibration_puts_data_in_working_range():
    """Sau hiệu chuẩn, Sdae trung vị của singleton phải ở quanh mục tiêu."""
    ds = generate_stream(300, 12, seed=9, calibrate_target=0.35)
    ltid = ds.ltid
    vals = []
    for nm in ds.eu:
        s = sum(
            (t.get(nm, 0.0) * ds.eu[nm]) / ds.inv_table[nm] * (0.8 ** (ltid - tid))
            for tid, t in ds.transactions.items() if t.get(nm, 0.0) > 0
        )
        if s > 0:
            vals.append(s)
    vals.sort()
    median = vals[len(vals) // 2]
    assert 0.15 < median < 0.8, f"trung vị Sdae lệch: {median}"


def test_builtin_datasets():
    keys = {d["key"] for d in list_datasets()}
    assert {"bang1_paper", "market_200", "market_1000"} <= keys
    ds = load_dataset("bang1_paper")
    assert ds.n_transactions == 8
    assert ds.n_items == 6
    # nạp lại trả về cùng đối tượng (cache)
    assert load_dataset("bang1_paper") is ds
    with pytest.raises(ValueError):
        load_dataset("khong_ton_tai")


def test_csv_roundtrip():
    ds = generate_stream(30, 6, seed=4)
    csv = stream_to_csv(ds.transactions)
    back = parse_csv(csv)
    assert set(back) == set(ds.transactions)
    for tid, tmap in ds.transactions.items():
        assert back[tid] == tmap


def test_parse_csv_variants():
    assert parse_csv("1,a,2\n2,b,1\n") == {1: {"a": 2.0}, 2: {"b": 1.0}}
    assert parse_csv("1;a;2\n") == {1: {"a": 2.0}}
    # gộp nhiều dòng cùng item
    assert parse_csv("1,a,1\n1,a,2\n") == {1: {"a": 3.0}}
    with pytest.raises(ValueError):
        parse_csv("")
    with pytest.raises(ValueError):
        parse_csv("1,a,-1\n")


# ------------------------------------------------------------------ bench
def test_run_benchmark_agrees_with_ground_truth():
    r = run_benchmark(60, 7, seed=2, f=0.8, minae=0.2)
    assert r["sound"] is True
    assert r["agreement"] == 1.0
    assert r["missing"] == []
    assert r["exact_ms"] > 0
    assert r["pruned_ms"] > 0


def test_scalability_returns_rows():
    r = run_scalability([{"transactions": 30, "items": 6},
                          {"transactions": 60, "items": 8}], with_exact=True)
    assert len(r["rows"]) == 2
    assert all("pruned_ms" in row for row in r["rows"])


def test_sweep_covers_grid():
    from app.core.data import EU, INV

    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    r = run_sweep(m, [0.7, 0.9], [0.1, 0.3])
    assert len(r["rows"]) == 4
    assert {row["f"] for row in r["rows"]} == {0.7, 0.9}


def test_sweep_does_not_disturb_source_miner():
    from app.core.data import EU, INV

    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    m.mine(f=0.8, minae=0.2)
    before = list(m.results)
    run_sweep(m, [0.5, 0.6], [0.1])
    assert m.results == before, "sweep phải chạy trên bản sao, không đụng miner gốc"


def test_clone_miner_is_independent():
    from app.core.data import EU, INV

    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    c = clone_miner(m)
    c.construction(99, [("a", 1)])
    assert 99 not in m.transactions
    assert 99 in c.transactions


def test_construction_cost_is_linear():
    """Pha 1 phải O(|T_j|): thời gian mỗi GD không phình theo độ dài luồng."""
    r = measure_construction_cost(300, 10, seed=8)
    assert r["growth_ratio"] is not None
    assert r["growth_ratio"] < 3.0, r
    assert r["bulk_ms"] > 0


def test_pruning_comparison_reports_both_strategies():
    r = run_pruning_comparison(200, 10, 8, seed=6)
    strategies = {row["strategy"]: row for row in r["rows"]}
    assert strategies["sound"]["sound"] is True
    assert strategies["sound"]["agreement"] == 1.0
    assert strategies["legacy"]["extra"] == []
    assert r["exact_ms"] > 0
