"""Backend nâng cấp — validation / tính nghiêm ngặt (strict) & healthcheck.

Các test regression cho các thay đổi nâng cấp backend:
  - `tid` phải là StrictInt > 0 (từ chối 2.5 / "8" / 0 / âm).
  - `POST /api/mine`: f phải float trong (0,1); minae >= 0; `sound` phải StrictBool.
  - `GET /api/health` trả về trạng thái nền tảng.
  - item không đăng ký → 400 (không 500); item/qty rỗng → 422.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    """Mỗi test bật lại luồng mặc định Bảng 1 để độc lập."""
    client.post("/api/reset")
    client.post("/api/load-example")
    yield


# ------------------------------------------------------------------ health
def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "HAEIM_Damped"
    assert body["transactions"] == 8
    assert body["ltid"] == 8


# ------------------------------------------------------------------ transaction strict
def test_tid_must_be_strict_positive_int():
    # tid không hợp lệ (type/âm/zero) -> 422 (validation lỏng trước, nay strict)
    assert client.post("/api/transactions", json={"tid": 0, "items": [{"item": "a", "qty": 1}]}).status_code == 422
    assert client.post("/api/transactions", json={"tid": -2, "items": [{"item": "a", "qty": 1}]}).status_code == 422
    assert client.post("/api/transactions", json={"tid": 2.5, "items": [{"item": "a", "qty": 1}]}).status_code == 422
    assert client.post("/api/transactions", json={"tid": "8", "items": [{"item": "a", "qty": 1}]}).status_code == 422
    # tid hợp lệ (số nguyên dương) -> 200
    assert client.post("/api/transactions", json={"tid": 9, "items": [{"item": "a", "qty": 1}]}).status_code == 200


def test_transaction_items_must_be_strictly_valid():
    # danh sách rỗng -> 422 (min_length)
    assert client.post("/api/transactions", json={"items": []}).status_code == 422
    # qty <= 0 -> 422 (gt=0)
    assert client.post("/api/transactions", json={"items": [{"item": "a", "qty": 0}]}).status_code == 422
    # item chưa đăng ký EU/INV -> 400 (lớp nghiệp vụ, không phải 500)
    assert client.post("/api/transactions", json={"items": [{"item": "zz", "qty": 1}]}).status_code == 400


# ------------------------------------------------------------------ mine strict
def test_mine_params_must_be_strict_and_in_range():
    # f ngoài (0,1) -> 422
    assert client.post("/api/mine", json={"f": 0.0, "minae": 0.2}).status_code == 422
    assert client.post("/api/mine", json={"f": 1.0, "minae": 0.2}).status_code == 422
    # minae âm -> 422
    assert client.post("/api/mine", json={"f": 0.8, "minae": -0.1}).status_code == 422
    # sound PHẢI là boolean JSON thật -> "true" (string) phải bị 422
    assert client.post("/api/mine", json={"f": 0.8, "minae": 0.2, "sound": "true"}).status_code == 422
    assert client.post("/api/mine", json={"f": 0.8, "minae": 0.2, "sound": True}).status_code == 200


# ------------------------------------------------------------------ explain strict
def test_explain_rejects_unknown_or_empty_pattern():
    # item chưa đăng ký -> 400 (ValueError được map ở layer HTTP)
    r = client.get("/api/explain", params={"pattern": "a,zz", "f": 0.8, "minae": 0.2})
    assert r.status_code == 400
    # pattern rỗng -> 400
    assert client.get("/api/explain", params={"pattern": "", "f": 0.8, "minae": 0.2}).status_code == 400
