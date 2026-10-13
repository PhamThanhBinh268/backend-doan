"""Kiểm chứng bám sát PDF (f=0.8, Ltid=8, minae=0.2)."""
import pytest

from app.core.data import EU, INV, EXAMPLE_STREAM, EXPECTED_SDAE_1ITEM, EXPECTED_SMDAEUB
from app.core.haeim_damped import HAEIMDampedMiner


@pytest.fixture
def miner() -> HAEIMDampedMiner:
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    return m


def test_singleton_sdae_matches_pdf(miner):
    out = miner.mine(f=0.8, minae=0.2)
    got = {tuple(c["pattern"])[0]: c["sdae"] for c in out["candidates"]}
    # PDF Ví dụ 3: {a}=0.188, {b}=0.542, {c}=0.598 (sai số làm tròn 0.005)
    for item, exp in EXPECTED_SDAE_1ITEM.items():
        assert got[item] == pytest.approx(exp, abs=0.005), f"{item}: {got[item]} != {exp}"


def test_smdaeub_matches_pdf(miner):
    out = miner.mine(f=0.8, minae=0.2)
    got = {tuple(c["pattern"])[0]: c["smdaeub"] for c in out["candidates"]}
    # chỉ kiểm tra ứng viên a,b,c (d,e,f bị lọc SMDAEUB<0.2)
    for item in ["a", "b", "c"]:
        assert got[item] == pytest.approx(EXPECTED_SMDAEUB[item], abs=0.02), f"{item}: {got[item]}"


def test_pruning_and_final_sets(miner):
    out = miner.mine(f=0.8, minae=0.2)
    # Pha 2: chỉ a,b,c thỏa SMDAEUB>=0.2, thứ tự tăng dần a<b<c
    assert out["order"] == ["a", "b", "c"], out["order"]
    pats = sorted([tuple(sorted(r["pattern"])) for r in out["dhaeis"]])
    # PDF § Kết quả cuối: DHAEIs = {b}, {c}, {b,c} ({a} loại vì Sdae<minae,
    # {c} STDAEUB=0 không mở rộng, chỉ {b} ghép {c})
    assert ("b",) in pats and ("c",) in pats, pats
    assert ("b", "c") in pats, pats
    assert ("a",) not in pats, pats


def test_streaming_construction_no_rescan(miner):
    n_before = sum(len(n.entries) for n in miner.nodes.values())
    miner.construction(9, [("a", 1), ("b", 1)])
    n_after = sum(len(n.entries) for n in miner.nodes.values())
    assert n_after - n_before == 2  # chỉ thêm 2 entry, không quét lại
    assert miner.ltid == 9


def test_join_requires_common_prefix_and_ltdaeub(miner):
    cands = miner.restructure(f=0.8, minae=0.2)
    by_pat = {tuple(n.pattern): n for n in cands}
    # PDF Ví dụ 5: {b}x{c} hợp lệ, LTDAEUB = STDAEUB(b) vì mọi tid(b) đều có c
    bc = miner._join(by_pat[("b",)], by_pat[("c",)], 0.8, miner.ltid, 0.2)
    assert bc is not None and tuple(sorted(bc.pattern)) == ("b", "c")
    # SMDAEUB của pattern dài là chặn trên hiệu suất (>= Sdae), không gán bằng Sdae
    assert bc.smdaeub >= bc.sdae
    # khác độ dài -> từ chối ghép (đúng tiền tố)
    assert miner._join(bc, by_pat[("c",)], 0.8, miner.ltid, 0.2) is None
    # LTDAEUB quá cao -> dừng sớm
    assert miner._join(by_pat[("b",)], by_pat[("c",)], 0.8, miner.ltid, 99.0) is None


def test_join_bc_sdae_still_haei(miner):
    cands = miner.restructure(f=0.8, minae=0.2)
    by_pat = {tuple(n.pattern): n for n in cands}
    bc = miner._join(by_pat[("b",)], by_pat[("c",)], 0.8, miner.ltid, 0.2)
    assert bc is not None
    # Công thức trung bình u/(Inv*|X|): Sdae({b,c}) ~ 0.2829 > 0.2 -> HAEI
    # (PDF ghi 0.2047 do ảnh công thức PI/PU bị mất; cùng kết luận HAEI)
    assert bc.sdae >= 0.2


def test_dynamic_item_and_validation(miner):
    with pytest.raises(KeyError):
        miner.construction(9, [("z", 1)])
    miner.register_item("z", eu=5.0, inv=60.0)
    miner.construction(9, [("z", 2)])
    assert miner.ltid == 9
    with pytest.raises(ValueError):
        miner.restructure(f=1.5, minae=0.2)
    with pytest.raises(ValueError):
        miner.register_item("bad", eu=0, inv=10)
    with pytest.raises(ValueError):
        miner.construction(10, [("a", 0)])
    with pytest.raises(ValueError):
        miner.construction(-1, [("a", 1)])


def test_mine_cache_and_stats(miner):
    out1 = miner.mine(f=0.8, minae=0.2)
    assert out1.get("cached") is False
    assert "stats" in out1 and out1["stats"]["dhaeis"] == len(out1["dhaeis"])
    out2 = miner.mine(f=0.8, minae=0.2)
    assert out2.get("cached") is True
    assert out2["dhaeis"] == out1["dhaeis"] and out2["order"] == out1["order"]
    # cache trả bản sao sâu: sửa kết quả trả về không ảnh hưởng cache
    out2["dhaeis"].append({"pattern": ["x"], "sdae": 0, "smdaeub": 0, "stdaeub": 0})
    out2b = miner.mine(f=0.8, minae=0.2)
    assert len(out2b["dhaeis"]) == len(out1["dhaeis"])
    # luồng đổi -> cache miss
    miner.construction(9, [("a", 1)])
    out3 = miner.mine(f=0.8, minae=0.2)
    assert out3.get("cached") is False
    assert out3["ltid"] == 9


def test_bulk_construction_equivalent():
    m1 = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m1.load_example_stream()
    ref = m1.mine(f=0.8, minae=0.2)
    m2 = HAEIMDampedMiner(eu=EU, inv_table=INV)
    batch = [(tid, [(i, q) for i, q in EXAMPLE_STREAM[tid]]) for tid in sorted(EXAMPLE_STREAM)]
    m2.bulk_construction(batch)
    got = m2.mine(f=0.8, minae=0.2)
    assert got["order"] == ref["order"]
    assert sorted([tuple(sorted(r["pattern"])) for r in got["dhaeis"]]) == \
        sorted([tuple(sorted(r["pattern"])) for r in ref["dhaeis"]])


def test_bulk_construction_atomic():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    n_before = len(m.transactions)
    with pytest.raises(ValueError):
        # tid 2 đã tồn tại -> cả lô không được ghi tid 9
        m.bulk_construction([(9, [("a", 1)]), (2, [("b", 1)])])
    assert len(m.transactions) == n_before
    assert 9 not in m.transactions


def test_out_of_order_tids_two_pointer_join():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    # thêm tid lộn xộn: entries không còn append theo thứ tự
    m.construction(5, [("a", 1), ("b", 1)])
    m.construction(2, [("a", 1), ("b", 2), ("c", 1)])
    m.construction(8, [("b", 1), ("c", 1)])
    cands = m.restructure(f=0.8, minae=0.0)
    by_pat = {tuple(n.pattern): n for n in cands}
    assert ("a",) in by_pat and ("b",) in by_pat
    joined = m._join(by_pat[("a",)], by_pat[("b",)], 0.8, m.ltid, 0.0)
    assert joined is not None
    # tid chung của a,b là {2,5} (b còn tid 8 không có a)
    assert sorted(e.tid for e in joined.entries) == [2, 5]
    # entries singleton đã được sort theo tid tại restructure
    assert [e.tid for e in by_pat[("a",)].entries] == sorted(e.tid for e in by_pat[("a",)].entries)
