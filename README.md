# StoneInventory

Phase 1 household inventory backend, deployed to a dedicated project directory on Debian.
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

Then visit http://localhost:8765/docs. This is API documentation, not the future household web UI.
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
now; the browser workflow comes in Phase 3. Local scans never call an external provider in Phase 1.

Every inventory operation requires a UUID request_id. Generate it once per intentional operation,
and reuse it for retries after timeouts or 503 responses. Repeated physical scans representing
different packages must have distinct IDs. Retrying returns the exact stored response.
Reusing an ID with changed input returns 409. Successful and rejected inventory operations are
remembered indefinitely, including insufficient-stock errors; a genuinely new attempt needs a new ID.
Malformed input rejected before an operation is not persisted.
SQLite BEGIN IMMEDIATE serializes writers. Inventory, audit, and saved response commit together.
RECONCILE has its own action, even when it changes nothing; its delta is never consumption.
No consumption analytics, recipes, product enrichment, web UI, or firmware are implemented yet.

Nutrition stores calories/macros, fiber, sugar, sodium, explicit measurement basis, serving size,
servings per package, ingredients, allergens, and dietary labels. Unknown nutrition remains null.
The schema reserves source payload, source ID, image, and fetched timestamp for later enrichment.
Package counts alone do not measure individual servings eaten. Nutrition/recipe calculations are
future work. Product metadata uses full replacement via PUT; supply fields you want to retain.

Schema v1 uses SQLite user_version; new versions must add explicit migrations, never recreate data.
Dependencies have tested direct pins; transitive dependencies are not yet locked.
See docs/DECISIONS.md and docs/BACKUPS.md.
