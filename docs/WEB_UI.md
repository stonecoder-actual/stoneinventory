# Household browser interface

The responsive interface is served at / by the same FastAPI container; /assets holds local CSS/JS.
No frontend framework, Node runtime, CDN, external fonts, or image fetches are required.
All reads and writes use the existing same-origin API. Inventory remains authoritative on Debian.
Network binding is still server loopback only. Use SSH port forwarding and visit http://localhost:8765/.
Phone/LAN access and authentication remain separate decisions, not part of this deployment.

## Workflows

- Inventory: search name/brand/barcode/category; sort by name, quantity, or updated time.
- Shopping list: products at or below minimum count, with max(0,target-current) suggested purchase count.
  Set a target higher than the minimum to obtain useful purchase recommendations.
- Needs a name: unresolved barcode queue. Identify once without changing its count/history.
- Product detail: current packages, minimum/target, source, nutrition/ingredients, ordered history.
- Add product: creates product details at zero packages. Use Correct count to establish physical count.
- Edit product: name, brand, package, category, thresholds, nutrition, ingredients, allergens, labels.
  The editor submits all editable fields to preserve existing values. Blank nutrition is unknown, not zero.
- Correct count: enter the actual count, review before/after, then confirm.
  Every correction is RECONCILE, never ADD/REMOVE or inferred consumption.

## Reliability

Reconciliation optionally accepts expected_quantity. If the server count no longer matches,
409 is returned with no count/audit change; reopen the product and review the updated count.
The UI always supplies this guard. Existing clients without it retain their previous behavior.
Payload serialization omits a missing guard to preserve saved pre-Phase-3 idempotency responses.
There is no new database schema migration in Phase 3.

Before sending a correction the browser stores its UUID and payload in sessionStorage.
After timeout/lost response, Retry safely reuses the identical request. This survives same-tab reloads.
The UI blocks another correction while a request awaits a confirmed response. A 4xx rejection clears it;
network/5xx errors preserve it. Retry is user-triggered; no background writes occur.
Keep the original tab open after uncertain results. sessionStorage does not survive closing a tab/browser
and is not shared across tabs. The next deliberate correction should follow reviewing current state.

Product metadata replacement uses idempotent PUT. Metadata edits are last-writer-wins; unlike count
corrections they do not yet have a concurrent-edit conflict check.

Imported/user product text is inserted with textContent, not HTML. The app sends a content security
policy restricting scripts, styles, connections, and images to the local app; there is no inline script.
An attribution link identifies Open Food Facts. Source data remains community/unverified until manual
verification. Nutrition editing does not implement meal/calorie consumption calculations.

## Verification

Backend regression:
```sh
sh scripts/test.sh
```

Isolated desktop/mobile browser checks (temporary database, external networking disabled):
```sh
docker build -f qa/Dockerfile -t stoneinventory-browser-tests .
docker run --rm --network none -v "$PWD/qa/results:/results" stoneinventory-browser-tests
```

Browser image is QA-only and not part of the running service. Screenshots in qa/results are ignored
by Git. No sample household records are inserted into the live database by browser tests.
