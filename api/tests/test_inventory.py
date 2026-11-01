import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app, database
from app.backup import backup

BARCODE = "001234567890"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOKUP_ENABLED", "0")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "inventory.sqlite3"))
    with TestClient(app) as client:
        yield client


def operation(client, action="add", quantity=1, request_id=None, barcode=BARCODE):
    data = {"request_id": request_id or str(uuid4()), "barcode": barcode,
            "device_id": "test", "quantity": quantity}
    if action == "reconcile":
        return client.post("/api/inventory/reconcile", json=data)
    return client.post("/api/scan", json={**data, "action": action})


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_known_product_sequence(client):
    assert client.put(f"/api/products/{BARCODE}", json={"name": "Rice"}).status_code == 200
    assert operation(client).json()["inventory"] == {"before": 0, "after": 1}
    assert operation(client).json()["inventory"]["after"] == 2
    assert operation(client, "remove").json()["inventory"]["after"] == 1
    history = client.get(f"/api/products/{BARCODE}/transactions").json()
    assert [t["action"] for t in history] == ["ADD", "ADD", "REMOVE"]


def test_remove_zero_no_false_consumption(client):
    assert operation(client, "remove").status_code == 409
    assert client.get(f"/api/products/{BARCODE}/transactions").json() == []


def test_reconciliation(client):
    for count in (5, 2, 0):
        assert operation(client, "reconcile", count).json()["inventory"]["after"] == count
    history = client.get(f"/api/products/{BARCODE}/transactions").json()
    assert [t["action"] for t in history] == ["RECONCILE"] * 3
    assert [(t["quantity_before"], t["quantity_after"]) for t in history] == [(0, 5), (5, 2), (2, 0)]


def test_unknown_identification_keeps_count_and_nutrition(client):
    result = operation(client).json()
    assert result["product"]["unresolved"] is True
    assert result["product"]["name"] is None
    assert len(client.get("/api/products?unresolved=true").json()) == 1
    update = client.put(f"/api/products/{BARCODE}", json={
        "name": "Rice", "serving_size": "45 g", "servings_per_package": 10,
        "ingredients": "Rice", "nutrition": {"basis": "per_serving", "calories_kcal": 160, "protein_g": 3}
    }).json()
    assert update["quantity"] == 1
    assert update["nutrition"]["protein_g"] == 3
    assert update["nutrition"]["fat_g"] is None
    assert update["barcode"] == BARCODE
    assert client.get("/api/products?unresolved=true").json() == []


def test_duplicate_persists_across_clients(client):
    request_id = str(uuid4())
    first = operation(client, request_id=request_id)
    with TestClient(app) as second:
        replay = operation(second, request_id=request_id)
    assert replay.json() == first.json()
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 1
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 1


def test_id_reuse_conflict(client):
    request_id = str(uuid4())
    operation(client, request_id=request_id)
    assert operation(client, "remove", request_id=request_id).status_code == 409


def test_failed_request_replay_does_not_remove_later_stock(client):
    request_id = str(uuid4())
    first = operation(client, "remove", request_id=request_id)
    operation(client)
    replay = operation(client, "remove", request_id=request_id)
    assert replay.status_code == 409
    assert first.json() == replay.json()
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 1


@pytest.mark.parametrize("changes", [
    {"barcode": 12345678}, {"barcode": "abc"}, {"barcode": "123"},
    {"action": "bogus"}, {"quantity": -1}, {"quantity": 0},
    {"quantity": True}, {"quantity": 1.5}, {"quantity": "1"},
    {"request_id": "bad"}, {"device_id": ""}, {"extra": "value"}
])
def test_invalid_input(client, changes):
    body = {"request_id": str(uuid4()), "barcode": BARCODE, "device_id": "test", "action": "add", "quantity": 1}
    body.update(changes)
    assert client.post("/api/scan", json=body).status_code == 422


def test_concurrent_updates_and_duplicate_delivery(client):
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: operation(client), range(24)))
    assert all(r.status_code == 200 for r in responses)
    request_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: operation(client, request_id=request_id), range(12)))
    assert all(r.json() == responses[0].json() for r in responses)
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 25
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 25


def test_backup_restore_and_retention(client, tmp_path, monkeypatch):
    import os
    operation(client)
    source = os.environ["DATABASE_PATH"]
    destination = tmp_path / "backups"
    for _ in range(3):
        snapshot = backup(source, destination, retention=2)
    assert len(list(destination.glob("*.sqlite3"))) == 2
    monkeypatch.setenv("DATABASE_PATH", str(snapshot))
    with TestClient(app) as restored:
        assert restored.get(f"/api/products/{BARCODE}").json()["quantity"] == 1
        assert len(restored.get(f"/api/products/{BARCODE}/transactions").json()) == 1


def test_database_failure_is_not_success(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path))
    assert operation(client).status_code == 503


def test_transaction_rollback(client):
    operation(client)
    with database() as db:
        db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON transactions BEGIN SELECT RAISE(ABORT, 'test'); END")
    assert operation(client).status_code == 503
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 1
