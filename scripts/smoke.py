"""Exercise a running API using actual HTTP. Leaves an identified test item at zero."""
import json
import urllib.request
from uuid import uuid4

BASE = "http://127.0.0.1:8765/api"
BARCODE = "0000000000000"


def call(path, payload=None, method=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.load(response)
    print(json.dumps({"path": path, "result": result}))
    return result


def operate(action, quantity=1, request_id=None):
    payload = {"request_id": request_id or str(uuid4()), "barcode": BARCODE,
               "quantity": quantity, "device_id": "development-smoke"}
    path = "/inventory/reconcile" if action == "reconcile" else "/scan"
    if action != "reconcile":
        payload["action"] = action
    return call(path, payload)


assert call("/health")["status"] == "ok"
call("/products/" + BARCODE, {"name": "DEVELOPMENT TEST ITEM - not household stock"}, "PUT")
operate("reconcile", 0)
first = operate("add")
assert first["inventory"]["after"] == 1
assert operate("add", request_id=first["request_id"]) == first
assert operate("add")["inventory"]["after"] == 2
assert operate("remove")["inventory"]["after"] == 1
assert operate("reconcile", 5)["inventory"]["after"] == 5
assert operate("reconcile", 0)["inventory"]["after"] == 0
history = call("/products/" + BARCODE + "/transactions")
assert [row["action"] for row in history[-6:]] == ["RECONCILE", "ADD", "ADD", "REMOVE", "RECONCILE", "RECONCILE"]
print("HTTP smoke passed: health, product, ADD/ADD/REMOVE/RECONCILE, replay, history.")
