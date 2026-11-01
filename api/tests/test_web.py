from uuid import uuid4
from test_inventory import client, operation, BARCODE


def test_web_assets_and_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Know what" in response.text
    assert 'script-src' in response.headers["content-security-policy"]
    for path in ("/assets/app.js", "/assets/style.css"):
        assert client.get(path).status_code == 200
    assert client.get("/assets/../main.py").status_code == 404


def test_stale_reconciliation_preserves_count_and_audit(client):
    operation(client)
    result = client.post("/api/inventory/reconcile", json={
        "request_id": str(uuid4()), "barcode": BARCODE, "device_id": "web",
        "quantity": 5, "expected_quantity": 0
    })
    assert result.status_code == 409
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 1
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 1


def test_matching_expected_count_and_duplicate_replay(client):
    operation(client)
    body = {"request_id": str(uuid4()), "barcode": BARCODE, "device_id": "web",
            "quantity": 5, "expected_quantity": 1}
    first = client.post("/api/inventory/reconcile", json=body)
    assert first.status_code == 200
    assert client.post("/api/inventory/reconcile", json=body).json() == first.json()
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 2


def test_reconcile_without_guard_keeps_original_payload_format(client):
    from app.main import database
    import json
    result = operation(client, "reconcile", 5).json()
    with database() as db:
        saved = json.loads(db.execute("SELECT payload FROM requests WHERE request_id=?", (result["request_id"],)).fetchone()[0])
    assert "expected_quantity" not in saved
    assert operation(client, "reconcile", 5, request_id=result["request_id"]).json() == result


def test_metadata_edit_never_changes_inventory_history(client):
    operation(client)
    response = client.put(f"/api/products/{BARCODE}", json={
        "name": "Oats", "minimum_quantity": 2, "target_quantity": 5,
        "nutrition": {"basis": "per_serving", "calories_kcal": 150, "protein_g": 4}
    }).json()
    assert response["quantity"] == 1
    assert response["nutrition"]["protein_g"] == 4
    assert response["minimum_quantity"] == 2
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 1
