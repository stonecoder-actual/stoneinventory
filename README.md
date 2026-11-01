# StoneInventory

Phase 3 household inventory application, deployed to a dedicated project directory on Debian.
The server is authoritative. The laptop is only a development and SSH client.

## Run

```sh
mkdir -p data backups
docker compose up -d --build
curl -f http://127.0.0.1:8765/api/health
sh scripts/test.sh
python3 scripts/smoke.py
docker compose logs --tail 100 api backup
```

No Python installation on the host is needed except for the optional smoke script.
Containers run as UID/GID 1000; bind-mount directories must be writable by that identity.
The API port is deliberately published only on loopback. No authentication is implemented.
To open the interactive API docs from the laptop, use a separate SSH session:

```sh
ssh -L 8765:127.0.0.1:8765 YOUR_USER@YOUR_SERVER
```

Then visit http://localhost:8765/ for the household interface. API documentation remains at /docs.
LAN exposure/authentication must be decided before connecting firmware or serving other devices.

## API and correctness

- GET /api/health: database availability.
- PUT /api/products/{barcode}: create or replace manual product details and thresholds without changing count.
- GET /api/products, optionally ?unresolved=true: local product records and inventory.
- GET /api/products/{barcode}: one local product record.
- POST /api/scan: add/remove with barcode, action, quantity, device_id, request_id.
- POST /api/inventory/reconcile: set absolute quantity with barcode, quantity, device_id, request_id.
- GET /api/products/{barcode}/transactions: ordered inventory audit history.

Barcodes are digit strings of length 8–14, preserving leading zeros. No checksum normalization yet.
Package counts are strict integers, 0–1,000,000. Add/remove quantities must be positive.
A new unknown ADD creates a nameless unresolved product and increases its count.
Unknown REMOVE cannot consume nonexistent stock. Unresolved records can be identified via the API
through the browser interface. New unresolved ADD scans try Open Food Facts; known products resolve locally.

Every inventory operation requires a UUID request_id. Generate it once per intentional operation,
and reuse it for retries after timeouts or 503 responses. Repeated physical scans representing
different packages must have distinct IDs. Retrying returns the exact stored response.
Reusing an ID with changed input returns 409. Successful and rejected inventory operations are
remembered indefinitely, including insufficient-stock errors; a genuinely new attempt needs a new ID.
Malformed input rejected before an operation is not persisted.
SQLite BEGIN IMMEDIATE serializes writers. Inventory, audit, and saved response commit together.
RECONCILE has its own action, even when it changes nothing; its delta is never consumption.
No consumption analytics, recipes, or firmware are implemented yet.

Nutrition stores calories/macros, fiber, sugar, sodium, explicit measurement basis, serving size,
servings per package, ingredients, allergens, and dietary labels. Unknown nutrition remains null.
Open Food Facts enrichment retains the source payload, source ID, image URL, and fetched timestamp locally.
Package counts alone do not measure individual servings eaten. Nutrition/recipe calculations are
future work. Product metadata uses full replacement via PUT; supply fields you want to retain.

Schema v2 uses SQLite user_version and migrates existing v1 databases without replacing inventory/history.
Dependencies have tested direct pins; transitive dependencies are not yet locked.
See docs/DECISIONS.md and docs/BACKUPS.md.

See [Phase 2 product lookup](docs/PRODUCT_LOOKUP.md) for caching, attribution, privacy, and offline behavior.

See [browser interface](docs/WEB_UI.md) for household workflows and safe correction retries.
