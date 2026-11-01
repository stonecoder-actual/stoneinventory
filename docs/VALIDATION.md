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
