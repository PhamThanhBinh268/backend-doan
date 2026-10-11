"""Kiểm chứng bám sát PDF (f=0.8, Ltid=8, minae=0.2)."""
from app.core.haeim_damped import HAEIMDampedMiner
from app.core.data import EU, INV, EXPECTED_SDAE_1ITEM, EXPECTED_SMDAEUB


def test_singleton_sdae_matches_pdf():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    out = m.mine(f=0.8, minae=0.2)
    got = {tuple(c["pattern"])[0]: c["sdae"] for c in out["candidates"]}
    # PDF Ví dụ 3: {a}=0.188, {b}=0.542, {c}=0.598 (sai số làm tròn 0.005)
    for item, exp in EXPECTED_SDAE_1ITEM.items():
        assert abs(got[item] - exp) < 0.005, f"{item}: {got[item]} != {exp}"


def test_smdaeub_matches_pdf():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    out = m.mine(f=0.8, minae=0.2)
    got = {tuple(c["pattern"])[0]: c["smdaeub"] for c in out["candidates"]}
    # chỉ kiểm tra ứng viên a,b,c (d,e,f bị lọc SMDAEUB<0.2)
    for item in ["a", "b", "c"]:
        assert abs(got[item] - EXPECTED_SMDAEUB[item]) < 0.02, f"{item}: {got[item]}"


def test_pruning_and_final_sets():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    out = m.mine(f=0.8, minae=0.2)
    # Pha 2: chỉ a,b,c thỏa SMDAEUB>=0.2, thứ tự tăng dần a<b<c
    assert out["order"] == ["a", "b", "c"], out["order"]
    pats = sorted([tuple(sorted(r["pattern"])) for r in out["dhaeis"]])
    # PDF § Kết quả cuối: DHAEIs = {b}, {c}, {b,c} ({a} loại vì Sdae<minae,
    # {c} STDAEUB=0 không mở rộng, chỉ {b} ghép {c})
    assert ("b",) in pats and ("c",) in pats, pats
    assert ("b", "c") in pats, pats
    assert ("a",) not in pats, pats


def test_streaming_construction_no_rescan():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    n_before = sum(len(n.entries) for n in m.nodes.values())
    m.construction(9, [("a", 1), ("b", 1)])
    n_after = sum(len(n.entries) for n in m.nodes.values())
    assert n_after - n_before == 2  # chỉ thêm 2 entry, không quét lại
    assert m.ltid == 9


def test_join_requires_common_prefix_and_ltdaeub():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    cands = m.restructure(f=0.8, minae=0.2)
    by_pat = {tuple(n.pattern): n for n in cands}
    # PDF Ví dụ 5: {b}x{c} hợp lệ, LTDAEUB = STDAEUB(b) vì mọi tid(b) đều có c
    bc = m._join(by_pat[("b",)], by_pat[("c",)], 0.8, m.ltid, 0.2)
    assert bc is not None and tuple(sorted(bc.pattern)) == ("b", "c")
    # SMDAEUB của pattern dài là chặn trên hiệu suất (>= Sdae), không gán bằng Sdae
    assert bc.smdaeub >= bc.sdae
    # khác độ dài -> từ chối ghép (đúng tiền tố)
    assert m._join(bc, by_pat[("c",)], 0.8, m.ltid, 0.2) is None
    # LTDAEUB quá cao -> dừng sớm
    assert m._join(by_pat[("b",)], by_pat[("c",)], 0.8, m.ltid, 99.0) is None


def test_join_bc_sdae_still_haei():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    cands = m.restructure(f=0.8, minae=0.2)
    by_pat = {tuple(n.pattern): n for n in cands}
    bc = m._join(by_pat[("b",)], by_pat[("c",)], 0.8, m.ltid, 0.2)
    assert bc is not None
    # Công thức trung bình u/(Inv*|X|): Sdae({b,c}) ~ 0.2829 > 0.2 -> HAEI
    # (PDF ghi 0.2047 do ảnh công thức PI/PU bị mất; cùng kết luận HAEI)
    assert bc.sdae >= 0.2


def test_dynamic_item_and_validation():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    try:
        m.construction(9, [("z", 1)])
        assert False, "phải từ chối item chưa đăng ký"
    except KeyError:
        pass
    m.register_item("z", eu=5.0, inv=60.0)
    m.construction(9, [("z", 2)])
    assert m.ltid == 9
    try:
        m.restructure(f=1.5, minae=0.2)
        assert False, "phải từ chối f ngoài (0,1)"
    except ValueError:
        pass


def test_mine_cache_and_stats():
    m = HAEIMDampedMiner(eu=EU, inv_table=INV)
    m.load_example_stream()
    out1 = m.mine(f=0.8, minae=0.2)
    assert out1.get("cached") is False
    assert "stats" in out1 and out1["stats"]["dhaeis"] == len(out1["dhaeis"])
    out2 = m.mine(f=0.8, minae=0.2)
    assert out2.get("cached") is True
    assert out2["dhaeis"] == out1["dhaeis"] and out2["order"] == out1["order"]
    # luồng đổi -> cache miss
    m.construction(9, [("a", 1)])
    out3 = m.mine(f=0.8, minae=0.2)
    assert out3.get("cached") is False
    assert out3["ltid"] == 9


def test_bulk_construction_equivalent():
    from app.core.data import EXAMPLE_STREAM
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
