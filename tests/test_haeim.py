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
