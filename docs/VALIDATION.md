# Phase 1 validation

Validated on Debian 13 with Docker and Compose. No unrelated services changed.

- 24 automated tests passed (including parametrized validation cases).
- Live HTTP: health, manual product creation, ADD, duplicate replay, ADD, REMOVE,
  reconciliation to 5, reconciliation to zero, ordered transaction history.
- Final development item count: zero. Six genuine audit entries; retry added no entry.
- Concurrent tests: 24 distinct adds plus 12 deliveries of one request produced 25 total units.
- Simulated audit insertion failure rolled back inventory.
- Database errors returned 503, never a false success.
- Automated snapshot retention and restored product/history tests passed.
- Live backup container and one-shot backup succeeded after correcting WAL directory access.
- Live snapshot copied to an isolated temporary directory: integrity check passed,
  test quantity zero and six audit rows matched live API history.
- API container healthy; backup container running; only server loopback port 8765 published.
- Known non-blocking test warning: installed Starlette deprecates its httpx TestClient path.
- External product APIs are absent in Phase 1; provider success/failure/cache tests belong to Phase 2.

Project commands used:
```sh
mkdir -p data backups
docker compose build
sh scripts/test.sh
docker compose up -d
python3 scripts/smoke.py
docker compose run --rm --no-deps backup python -m app.backup
python3 scripts/verify-backup.py
docker compose ps
docker compose logs --tail 5 backup
```

Environment inspection used pwd, id, os-release, df, command -v, version queries, ss, and ls.
An isolated host Python venv attempt lacked ensurepip; it is unused. Tests run in Docker.
The first shell-quoted test invocation failed before running tests; portable script runner fixed it.
SCP required owner-write permissions on copied project directories before adding new files.

Remaining: off-server backups, transitive dependency lock, LAN/authentication decision before
device access, and optional TestClient dependency modernization. Phase 2 is not started.


## Phase 2 validation

- 56 tests passed; all provider responses and network failures mocked in the automated suite.
- Verified successful enrichment, local cache reuse, unknown and malformed responses, timeouts,
  disconnected responses, 404/429/503 errors, negative cache, global request budget, and retry cooldown.
- Concurrent unknown scans made one provider lookup while preserving both inventory updates.
- Manual product edits made during lookup won over external data.
- Replayed inventory requests returned the original result after later product identification.
- Version 1 migration retained inventory and audit history; live database upgraded to schema 2.
- Separate official staging integration check resolved sample barcode 3274080005003.
- Live HTTP health and ADD/ADD/REMOVE/RECONCILE/history/replay regression passed.
- Live resolution of a manual test product returned cached without contacting a provider.
- Fresh deployed backup restored into an isolated temporary directory; prior history retained.
- Existing non-blocking Starlette/httpx deprecation warning remains.
- No household web UI, firmware, or public/LAN exposure added.

Additional commands:
```sh
docker compose run --rm --no-deps -e PYTHONPATH=/app -e OFF_STAGING_AUTH -v "$PWD/scripts:/scripts:ro" api python /scripts/provider-check.py
curl -fsS -X POST http://127.0.0.1:8765/api/products/0000000000000/resolve
```

Provider behavior and attribution: docs/PRODUCT_LOOKUP.md.


## Phase 3 validation

- 61 API/regression tests passed, including browser asset serving/security headers, guarded
  reconciliation conflicts, duplicate replay, pre-guard payload compatibility, and metadata preservation.
- Isolated Chromium end-to-end suite passed with networking disabled and a temporary database.
- Browser checks: inventory search/empty state, low-stock filter and purchase quantity, unknown
  barcode identification, manual product creation, nutrition/threshold editing without count changes,
  review-before-confirm correction, rejection after another device changed stock, and replay after
  a successful response was lost followed by page reload.
- Text resembling HTML was rendered safely as text; no injected image/script nodes were created.
- Desktop (1440 px) and phone (390 px) screenshots inspected; no page-level horizontal overflow.
  Phone inventory rows show name, count, and status without sideways scrolling.
- A malformed per-serving selector found by browser QA was fixed and covered by a browser assertion.
- Deployment keeps the existing loopback binding, SQLite schema, household data, and backup services.
- Live root/assets/health and a fresh snapshot restoration checked after deployment.
- Browser fixtures/screenshot output are isolated from household data; screenshots are Git-ignored.
- Existing non-blocking Starlette/httpx deprecation warning remains.

Additional commands:
```sh
docker build -f qa/Dockerfile -t stoneinventory-browser-tests .
docker run --rm --network none -v "$PWD/qa/results:/results" stoneinventory-browser-tests
```

No meal-planning engine or firmware is included in this phase.

## Trusted LAN access validation

- Compose merged bindings verified: loopback plus the chosen LAN IPv4 address, no wildcard bind.
- Complete isolated browser workflow passed with randomUUID removed to exercise plain-HTTP UUID fallback.
- Laptop connected directly over LAN: page HTTP 200 and health ok.
- Server-specific address/configuration excluded from Git; no household data changed.

## CYD firmware compile verification

- cyd-diagnostics compiled successfully: 319497 bytes flash, 23028 bytes static RAM.
- cyd-terminal compiled successfully: 845149 bytes flash, 47492 bytes static RAM.
- Pinned Espressif32 6.10.0 / Arduino ESP32 2.0.17, TFT_eSPI 2.5.43, ArduinoJson 6.21.5, upstream XPT2046 commit.
- Touch uses its own VSPI bus; display uses HSPI.
- Expected TFT_eSPI warning: its built-in touch feature is disabled; XPT2046 is used instead.
- No firmware uploaded yet; physical behavior and scanner transport remain unverified.
- No backend, inventory, or database changes made for firmware compilation.


## Bluetooth scanner integration

- All three environments compiled locally on Windows: cyd-diagnostics (318361 bytes flash),
  cyd-scanner-test (1160677 bytes), and cyd-terminal (1610193 bytes).
- Native C++ parser/outbox tests passed on Debian: split frames, CRLF, leading zeros,
  repeated products, invalid and oversized frames, persisted FIFO ordering, reboot replay,
  failed storage, mismatched acknowledgements, and full-capacity rejection.
- New SPP scanner test makes no API calls or inventory writes; physical pairing is pending.
- Terminal uses background Bluetooth connection and HTTP tasks, a bounded byte receive queue,
  and a durable eight-operation outbox. Queue/receive/storage failures pause with explicit feedback.
- Standard huge_app table increases app space to 3 MB while retaining the existing NVS offset/size.
- Existing private Wi-Fi configuration was not read, changed, uploaded, or committed.
- No firmware was flashed automatically and no household inventory operations were performed.
- Remaining physical checks: SPP pairing/authentication, scanner suffix/framing, actual successive
  scans, Wi-Fi/Bluetooth loss/reconnect, server outage, power loss with pending operations,
  and terminal behavior while adding/removing/reconciling stock.
