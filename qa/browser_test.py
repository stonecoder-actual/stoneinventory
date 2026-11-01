"""Headless end-to-end QA against an isolated database, never household data."""
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OATS, MILK, UNKNOWN = "001234567890", "12345678", "99999999"


def api(path, body=None, method=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def count(barcode, quantity):
    return api("/api/inventory/reconcile", {"barcode": barcode, "quantity": quantity,
               "device_id": "browser-qa", "request_id": str(uuid4())})


with tempfile.TemporaryDirectory() as tmp:
    process = subprocess.Popen(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                               env={**os.environ, "DATABASE_PATH": str(Path(tmp)/"qa.sqlite3"), "LOOKUP_ENABLED": "0"})
    try:
        for _ in range(100):
            try:
                api("/api/health")
                break
            except OSError:
                time.sleep(0.1)
        api("/api/products/"+OATS, {"name":"Rolled oats","brand":"Pantry staples","package_size":"500 g",
            "category":"Pantry","minimum_quantity":2,"target_quantity":5,
            "nutrition":{"basis":"per_serving","calories_kcal":150,"protein_g":4}}, "PUT")
        count(OATS, 1)
        api("/api/products/"+MILK, {"name":"Whole milk","brand":"Everyday dairy","package_size":"1 litre","minimum_quantity":1,"target_quantity":3}, "PUT")
        count(MILK, 4)
        count(UNKNOWN, 2)
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width":1440,"height":1000})
            page.on("pageerror", lambda error: (errors.append(str(error)), print("BROWSER ERROR:", error, flush=True)))
            page.goto(BASE)
            page.get_by_role("button", name="Rolled oats", exact=True).wait_for()
            assert page.locator("#stat-all").inner_text() == "3"
            page.locator("#search").fill("no such product")
            assert page.get_by_text("No matching products", exact=True).is_visible()
            page.locator("#search").fill("")
            page.get_by_role("button",name="Low stock",exact=True).click()
            assert page.get_by_role("button",name="Rolled oats",exact=True).is_visible()
            assert not page.get_by_role("button",name="Whole milk",exact=True).is_visible()
            assert page.get_by_text("Buy 4",exact=True).is_visible()
            page.get_by_role("button",name="Unidentified",exact=True).click()
            page.get_by_role("button",name="Identify",exact=True).click()
            page.get_by_role("button",name="Identify product",exact=True).click()
            page.locator('#edit-form input[name="name"]').fill("Dish soap")
            page.get_by_role("button",name="Save product",exact=True).click()
            page.locator("#detail-title").filter(has_text="Dish soap").wait_for()
            assert api("/api/products/"+UNKNOWN)["quantity"] == 2
            assert len(api("/api/products/"+UNKNOWN+"/transactions")) == 1
            page.get_by_role("button",name="Close product details").click()
            page.get_by_role("button",name="All products",exact=True).click()
            page.get_by_role("button",name="Rolled oats",exact=True).click()
            page.get_by_role("button",name="Correct count",exact=True).click()
            page.locator("#new-count").fill("5")
            page.get_by_role("button",name="Review change",exact=True).click()
            assert api("/api/products/"+OATS)["quantity"] == 1
            page.get_by_role("button",name="Confirm correction",exact=True).click()
            page.locator("#detail-title").filter(has_text="Rolled oats").wait_for()
            assert api("/api/products/"+OATS)["quantity"] == 5
            assert api("/api/products/"+OATS+"/transactions")[-1]["action"] == "RECONCILE"
            # Metadata editing preserves macros and count.
            page.get_by_role("button",name="Edit product",exact=True).click()
            assert page.locator('#edit-form select[name="basis"]').input_value() == "per_serving"
            page.locator('#edit-form input[name="target_quantity"]').fill("8")
            assert page.locator("#edit-form").evaluate("form => form.checkValidity()"), page.locator("#edit-form input:invalid").evaluate_all("inputs => inputs.map(i => [i.name, i.value, i.validationMessage])")
            page.get_by_role("button",name="Save product",exact=True).click()
            page.locator("#detail-title").filter(has_text="Rolled oats").wait_for()
            assert api("/api/products/"+OATS)["nutrition"]["protein_g"] == 4
            # Another device changes the count while the correction form is open.
            page.get_by_role("button",name="Correct count",exact=True).click()
            count(OATS, 6)
            page.locator("#new-count").fill("9")
            page.get_by_role("button",name="Review change",exact=True).click()
            page.get_by_role("button",name="Confirm correction",exact=True).click()
            page.get_by_text("Count changed since you opened",exact=False).wait_for()
            assert api("/api/products/"+OATS)["quantity"] == 6
            # Lose a success response, reload, then replay the persisted ID.
            page.get_by_role("button",name="Rolled oats",exact=True).click()
            page.get_by_role("button",name="Correct count",exact=True).click()
            page.locator("#new-count").fill("7")
            page.get_by_role("button",name="Review change",exact=True).click()
            def lose_response(route):
                route.fetch()
                route.abort()
            page.route("**/api/inventory/reconcile", lose_response, times=1)
            page.get_by_role("button",name="Confirm correction",exact=True).click()
            page.get_by_text("The result is not confirmed",exact=False).wait_for()
            saved_count = len(api("/api/products/"+OATS+"/transactions"))
            page.reload()
            page.get_by_role("button",name="Retry safely",exact=True).click()
            page.locator("#detail-title").filter(has_text="Rolled oats").wait_for()
            assert api("/api/products/"+OATS)["quantity"] == 7
            assert len(api("/api/products/"+OATS+"/transactions")) == saved_count
            page.get_by_role("button",name="Close product details").click()
            # Product names are text, never executable markup.
            api("/api/products/11111111", {"name":"<img src=x onerror=alert(1)>"}, "PUT")
            page.get_by_role("button",name="Refresh",exact=False).click()
            page.get_by_role("button",name="<img src=x onerror=alert(1)>",exact=True).wait_for()
            assert page.locator("#rows img").count() == 0
            api("/api/products/11111111", {"name":"Olive oil","brand":"Kitchen essentials","package_size":"750 ml","minimum_quantity":1,"target_quantity":2}, "PUT")
            page.get_by_role("button",name="Add product",exact=False).click()
            page.locator('#edit-form input[name="barcode"]').fill("22222222")
            page.locator('#edit-form input[name="name"]').fill("Brown rice")
            page.get_by_role("button",name="Save product",exact=True).click()
            page.locator("#detail-title").filter(has_text="Brown rice").wait_for()
            assert api("/api/products/22222222")["quantity"] == 0
            page.get_by_role("button",name="Close product details").click()
            Path("/results").mkdir(exist_ok=True)
            page.screenshot(path="/results/desktop.png",full_page=True)
            page.set_viewport_size({"width":390,"height":844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert page.get_by_role("button",name="Add product",exact=False).is_visible()
            assert page.get_by_role("button",name="Rolled oats",exact=True).is_visible()
            page.screenshot(path="/results/mobile.png",full_page=True)
            page.get_by_role("button",name="Rolled oats",exact=True).click()
            page.locator("#detail-title").filter(has_text="Rolled oats").wait_for()
            assert page.get_by_role("button",name="Correct count",exact=True).is_visible()
            page.get_by_role("button",name="Close product details").click()
            assert not errors, errors
            browser.close()
        print("Browser QA passed: search, filters, unknown identification, nutrition preservation, confirmed correction, stale edit, lost-reply retry after reload, safe text rendering, desktop/mobile.")
    finally:
        process.terminate()
        process.wait(timeout=10)
