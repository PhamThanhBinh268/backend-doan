"""Kiểm thử tích hợp API (FastAPI TestClient)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    """Mỗi test bắt đầu với luồng mẫu Bảng 1 của PDF."""
    client.post("/api/reset")
    client.post("/api/load-example")
    yield


def test_root_and_config():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "HAEIM_Damped"
    assert body["transactions"] == 8
    assert body["ltid"] == 8
    assert body["default"]["f"] == 0.8

    r = client.get("/api/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["eu"]["a"] == 4.0
    assert cfg["inv"]["a"] == 96.0
    assert cfg["default_f"] == 0.8


def test_mine_matches_pdf_result():
    r = client.post("/api/mine", json={"f": 0.8, "minae": 0.2})
    assert r.status_code == 200
    body = r.json()
    pats = sorted(tuple(sorted(d["pattern"])) for d in body["dhaeis"])
    assert pats == [("b",), ("b", "c"), ("c",)]
    assert body["order"] == ["a", "b", "c"]
    assert body["cached"] is False
    # lần 2 -> cache
    r2 = client.post("/api/mine", json={"f": 0.8, "minae": 0.2})
    assert r2.json()["cached"] is True


def test_mine_rejects_invalid_params():
    # Lỗi tham số ở tầng schema -> 422 (chuẩn FastAPI/pydantic)
    assert client.post("/api/mine", json={"f": 1.5, "minae": 0.2}).status_code == 422
    assert client.post("/api/mine", json={"f": 0.0, "minae": 0.2}).status_code == 422
    assert client.post("/api/mine", json={"f": 0.8, "minae": -1}).status_code == 422


def test_transactions_crud():
    r = client.post("/api/transactions", json={"items": [{"item": "a", "qty": 1}]})
    assert r.status_code == 200
    assert r.json()["tid"] == 9
    # trùng tid -> 400
    assert client.post("/api/transactions", json={"tid": 9, "items": [{"item": "a", "qty": 1}]}).status_code == 400
    # item chưa đăng ký -> 400
    assert client.post("/api/transactions", json={"items": [{"item": "zz", "qty": 1}]}).status_code == 400
    # qty <= 0 -> 422 (pydantic)
    assert client.post("/api/transactions", json={"items": [{"item": "a", "qty": 0}]}).status_code == 422

    r = client.get("/api/transactions")
    assert len(r.json()["transactions"]) == 9


def test_bulk_transactions():
    r = client.post("/api/transactions/bulk", json={"transactions": [
        {"items": [{"item": "a", "qty": 1}]},
        {"tid": 20, "items": [{"item": "b", "qty": 2}]},
    ]})
    assert r.status_code == 200
    assert r.json()["loaded"] == 2
    # lô rỗng -> 422 (vi phạm min_length của schema)
    assert client.post("/api/transactions/bulk", json={"transactions": []}).status_code == 422


def test_validate_against_ground_truth():
    r = client.post("/api/validate", json={"f": 0.8, "minae": 0.2})
    assert r.status_code == 200
    body = r.json()
    assert body["sound"] is True
    assert body["agreement"] == 1.0
    assert body["missing"] == []
    assert body["exact"]["count"] == 3
    assert body["pruned"]["count"] == 3


def test_dae_lists_endpoint():
    client.post("/api/mine", json={"f": 0.8, "minae": 0.2})
    r = client.get("/api/dae-lists")
    assert r.status_code == 200
    body = r.json()
    assert body["order"] == ["a", "b", "c"]
    names = {tuple(n["pattern"]) for n in body["nodes"]}
    assert ("b",) in names
    # entry phải có đủ trường
    node = next(n for n in body["nodes"] if tuple(n["pattern"]) == ("b",))
    entry = node["entries"][0]
    for key in ("tid", "u", "ae", "maeub", "dae", "mdaeub", "tdaeub", "maxru", "minInv", "k"):
        assert key in entry


def test_dataset_generate_and_load():
    r = client.post("/api/dataset/generate", json={
        "n_transactions": 60, "n_items": 8, "seed": 5, "load": True})
    assert r.status_code == 200
    body = r.json()
    assert body["loaded"] == 60
    assert body["ltid"] == 60
    assert body["dataset"]["items"] == 8

    # tất định: cùng seed -> cùng kết quả
    r2 = client.post("/api/dataset/generate", json={
        "n_transactions": 60, "n_items": 8, "seed": 5, "load": False})
    assert r2.json()["sample"] == body["sample"]


def test_dataset_load_builtin():
    r = client.get("/api/datasets")
    assert r.status_code == 200
    assert any(d["key"] == "bang1_paper" for d in r.json()["datasets"])
    r = client.post("/api/dataset/load", json={"key": "bang1_paper"})
    assert r.status_code == 200
    assert r.json()["loaded"] == 8
    assert client.post("/api/dataset/load", json={"key": "khong_ton_tai"}).status_code == 400


def test_dataset_import_csv():
    csv = "tid,item,qty\n1,a,1\n1,b,2\n2,a,3\n"
    r = client.post("/api/dataset/import", json={"csv": csv, "load": True})
    assert r.status_code == 200
    body = r.json()
    assert body["transactions"] == 2
    assert body["items"] == 2
    # CSV sai định dạng -> 400
    assert client.post("/api/dataset/import", json={"csv": "abc"}).status_code == 400


def test_export_csv_and_json():
    client.post("/api/mine", json={"f": 0.8, "minae": 0.2})
    r = client.get("/api/export", params={"fmt": "csv"})
    assert r.status_code == 200
    assert "pattern,sdae" in r.text
    assert "{b}" in r.text
    r = client.get("/api/export", params={"fmt": "json"})
    assert r.status_code == 200
    assert len(r.json()["dhaeis"]) == 3
    assert client.get("/api/export", params={"fmt": "xml"}).status_code == 422


def test_explain_endpoint():
    r = client.get("/api/explain", params={"pattern": "b,c", "f": 0.8, "minae": 0.2})
    assert r.status_code == 200
    body = r.json()
    assert body["pattern"] == ["b", "c"]
    assert body["is_haei"] is True
    assert body["entries"], "phải có bảng đóng góp theo giao dịch"
    assert body["reasons"], "phải có lý do kết luận"
    # giải thích cả tập kết quả (cần khai thác trước)
    client.post("/api/mine", json={"f": 0.8, "minae": 0.2})
    r = client.get("/api/explain/all")
    assert r.status_code == 200
    assert r.json()["count"] == 3


def test_bench_and_sweep_endpoints():
    r = client.post("/api/bench", json={"n_transactions": 40, "n_items": 6, "seed": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["sound"] is True
    assert body["agreement"] == 1.0

    r = client.post("/api/sweep", json={"f_values": [0.7, 0.8], "minae_values": [0.1, 0.2]})
    assert r.status_code == 200
    assert len(r.json()["rows"]) == 4


def test_construction_cost_endpoint():
    r = client.post("/api/construction-cost", json={"n_transactions": 50, "n_items": 6})
    assert r.status_code == 200
    body = r.json()
    # O(|T_j|) -> thời gian mỗi GD không phình theo độ dài luồng
    assert body["growth_ratio"] is not None
    assert body["growth_ratio"] < 3.0


def test_metrics_endpoint():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["transactions"] == 8
    assert body["singleton_nodes"] == 6
    assert body["ltid"] == 8


def test_pruning_comparison_endpoint():
    r = client.post("/api/pruning-comparison", json={
        "n_transactions": 80, "n_items": 8, "max_items_per_tx": 6, "seed": 3})
    assert r.status_code == 200
    body = r.json()
    strategies = {row["strategy"]: row for row in body["rows"]}
    assert strategies["sound"]["sound"] is True
    assert strategies["sound"]["agreement"] == 1.0
    assert body["missed_by_legacy"] >= 0


def test_ui_and_openapi():
    assert client.get("/ui").status_code == 200
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in ("/api/mine", "/api/validate", "/api/bench", "/api/sweep",
              "/api/datasets", "/api/explain", "/api/metrics"):
        assert p in paths, f"thiếu endpoint {p}"
