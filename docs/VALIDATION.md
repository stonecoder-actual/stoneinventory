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
