import http.client
import json
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest
from app import lookup, main
from test_inventory import client, operation, BARCODE

RAW = {
    "code": BARCODE, "product_name": "Example oats", "brands": "Example",
    "quantity": "500 g", "serving_size": "50 g", "ingredients_text": "Oats",
    "allergens": "en:gluten", "labels": "en:vegan",
    "product_quantity": 500, "product_quantity_unit": "g",
    "serving_quantity": 50, "serving_quantity_unit": "g",
    "nutriments": {"energy-kcal_serving": 190, "proteins_serving": 6,
                   "sodium_serving": 0.002, "fat_serving": 4}
}


@pytest.fixture
def enabled(client, monkeypatch):
    monkeypatch.setenv("LOOKUP_ENABLED", "1")
    monkeypatch.setattr(main, "fetch_product", lambda barcode: ("not_found", None))
    return client


def test_success_cache_and_original_barcode(enabled, monkeypatch):
    calls = []
    def fetch(barcode):
        calls.append(barcode)
        return "found", lookup.normalize(RAW)
    monkeypatch.setattr(main, "fetch_product", fetch)
    first = operation(enabled).json()
    assert first["product"]["name"] == "Example oats"
    assert first["product"]["source"] == "openfoodfacts"
    assert first["product"]["nutrition"]["sodium_mg"] == 2
    assert first["product"]["servings_per_package"] == 10
    assert first["product"]["barcode"] == BARCODE
    assert first["product"]["source_payload"]["allergens"] == "en:gluten"
    assert not first["product"]["manually_verified"]
    assert first["product"]["source_fetched_at"]
    operation(enabled)
    assert enabled.post(f"/api/products/{BARCODE}/resolve").json()["lookup"] == "cached"
    assert calls == [BARCODE]


@pytest.mark.parametrize("outcome", ["not_found", "unavailable", "invalid_response", "incomplete"])
def test_failures_preserve_inventory_and_cool_down(enabled, monkeypatch, outcome):
    calls = []
    def fetch(barcode):
        calls.append(barcode)
        return outcome, None
    monkeypatch.setattr(main, "fetch_product", fetch)
    result = operation(enabled).json()
    assert result["product"]["unresolved"]
    assert result["inventory"]["after"] == 1
    operation(enabled)
    assert calls == [BARCODE]
    assert enabled.get(f"/api/products/{BARCODE}").json()["quantity"] == 2


def test_manual_identity_is_never_overwritten(enabled, monkeypatch):
    enabled.put(f"/api/products/{BARCODE}", json={"name": "My label"})
    def forbidden(barcode):
        raise AssertionError("Manual product must not trigger provider")
    monkeypatch.setattr(main, "fetch_product", forbidden)
    assert operation(enabled).json()["product"]["name"] == "My label"


def test_manual_edit_during_lookup_wins(enabled, monkeypatch):
    def fetch(barcode):
        enabled.put(f"/api/products/{barcode}", json={"name": "Manual wins"})
        return "found", lookup.normalize(RAW)
    monkeypatch.setattr(main, "fetch_product", fetch)
    assert operation(enabled).json()["product"]["name"] == "Manual wins"


def test_no_db_lock_during_network_and_one_lookup_for_simultaneous_scans(enabled, monkeypatch):
    from threading import Event
    started, release = Event(), Event()
    calls = []
    def fetch(barcode):
        calls.append(barcode)
        started.set()
        assert release.wait(5)
        return "found", lookup.normalize(RAW)
    monkeypatch.setattr(main, "fetch_product", fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(operation, enabled)
        assert started.wait(5)
        second = operation(enabled)
        assert second.status_code == 200
        release.set()
        assert first.result().status_code == 200
    assert calls == [BARCODE]
    assert enabled.get(f"/api/products/{BARCODE}").json()["quantity"] == 2


def test_global_budget_defers_other_product(enabled):
    operation(enabled)
    result = enabled.post("/api/products/12345678/resolve").json()
    assert result["lookup"] == "deferred"
    assert result["product"]["quantity"] == 0


def test_retry_after_cooldown(enabled, monkeypatch):
    operation(enabled)
    with main.database() as db:
        db.execute("UPDATE product_lookups SET next_attempt_at=0")
        db.execute("UPDATE lookup_budget SET next_attempt_at=0")
    monkeypatch.setattr(main, "fetch_product", lambda code: ("found", lookup.normalize(RAW)))
    result = enabled.post(f"/api/products/{BARCODE}/resolve").json()
    assert result["lookup"] == "found"
    assert result["product"]["quantity"] == 1


def test_exact_duplicate_response_after_later_identification(enabled):
    first = operation(enabled).json()
    enabled.put(f"/api/products/{BARCODE}", json={"name": "Now identified"})
    replay = operation(enabled, request_id=first["request_id"]).json()
    assert replay == first


def test_v1_migration_preserves_data(client):
    operation(client)
    with main.database() as db:
        db.executescript("DROP TABLE product_lookups; DROP TABLE lookup_budget; PRAGMA user_version=1;")
    main.initialize()
    with main.database() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert client.get(f"/api/products/{BARCODE}").json()["quantity"] == 1
    assert len(client.get(f"/api/products/{BARCODE}/transactions").json()) == 1


class Response:
    def __init__(self, content):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.content[:size]


def test_adapter_request_and_normalization(monkeypatch):
    def open_request(request, timeout):
        assert timeout == 3
        assert request.full_url == f"https://world.openfoodfacts.org/api/v3/product/{BARCODE}.json"
        assert "StoneInventory" in request.get_header("User-agent")
        return Response(json.dumps({"product": RAW}).encode())
    monkeypatch.setattr(lookup.urllib.request, "urlopen", open_request)
    outcome, result = lookup.fetch_product(BARCODE)
    assert outcome == "found"
    assert result["ingredients"] == "Oats"


@pytest.mark.parametrize("raw", [
    b"not json", b"[]", b'{"product": null}',
    b'{"product": {"code":"99999999","product_name":"Wrong"}}',
    b'{"product":{"code":"001234567890","product_name":"Bad","x":NaN}}',
    b"x" * (lookup.MAX_BYTES + 1)
])
def test_bad_provider_response(monkeypatch, raw):
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: Response(raw))
    outcome, fields = lookup.fetch_product(BARCODE)
    assert outcome in ("invalid_response", "unavailable")
    assert fields is None


@pytest.mark.parametrize("error", [
    TimeoutError(), urllib.error.URLError("offline"), http.client.IncompleteRead(b"partial"),
    urllib.error.HTTPError("https://example", 429, "rate limit", {}, None),
    urllib.error.HTTPError("https://example", 503, "unavailable", {}, None),
])
def test_adapter_network_errors(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(lookup.urllib.request, "urlopen", fail)
    assert lookup.fetch_product(BARCODE) == ("unavailable", None)


def test_missing_macros_stay_unknown():
    result = lookup.normalize({"product_name": "Water", "nutriments": {"sodium_100g": 0.001}})
    nutrition = json.loads(result["nutrition_json"])
    assert nutrition["sodium_mg"] == 1
    assert nutrition["protein_g"] is None
    assert nutrition["basis"] == "per_100g_or_100ml"
    assert lookup.normalize({"code": BARCODE}) is None


def test_nonfinite_and_negative_nutrients_ignored():
    result = lookup.normalize({"product_name": "Example", "nutriments": {"fat_100g": -1, "proteins_100g": "nan"}})
    assert result["nutrition_json"] == "{}"


def test_servings_not_invented_for_mismatched_units():
    assert lookup.normalize({**RAW, "serving_quantity_unit": "ml"})["servings_per_package"] is None


@pytest.mark.parametrize("data", [
    {"status": 0}, {"result": {"id": "product_not_found"}},
    {"product": {"code": BARCODE}}
])
def test_not_found_or_incomplete(monkeypatch, data):
    monkeypatch.setattr(lookup.urllib.request, "urlopen", lambda *a, **k: Response(json.dumps(data).encode()))
    outcome, fields = lookup.fetch_product(BARCODE)
    assert outcome in ("not_found", "incomplete")
    assert fields is None


def test_http_404_is_not_found(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://example", 404, "missing", {}, None)
    monkeypatch.setattr(lookup.urllib.request, "urlopen", fail)
    assert lookup.fetch_product(BARCODE) == ("not_found", None)


def test_staging_without_private_authorization_does_not_call_network(monkeypatch):
    monkeypatch.setenv("OFF_STAGING", "1")
    monkeypatch.delenv("OFF_STAGING_AUTH", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Staging requires private authorization")
    monkeypatch.setattr(lookup.urllib.request, "urlopen", forbidden)
    assert lookup.fetch_product(BARCODE) == ("unavailable", None)
