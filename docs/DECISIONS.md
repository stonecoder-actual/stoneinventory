# Accepted scope and decisions

- Development: personal Windows laptop over SSH; Debian runs independently after deployment.
- Firmware flashing/serial: laptop USB only. Scanner transport deferred until hardware arrives.
- GitHub owner: stonecoder-actual; repository: public stoneinventory; runtime data excluded.
- V1: mandatory duplicate-request protection and consistent daily local SQLite backups.
- Unknown ADD: retain barcode/count and flag for later browser identification.
- Quantities: integer packages, not partial grams or portions.
- Product data: retain local identity and meal/nutrition fields for later planning.
- Phase 1: core API, local products, audit, tests, backups. No external API lookup yet.
- SQLite standard-library database layer avoids unnecessary ORM/migration dependencies;
  user_version provides an explicit version boundary for future migration scripts.
- Dedicated backup container avoids installing cron or changing host services.
- No other Docker services, firewall rules, or server configuration are managed by this project.
- Docker access for sam was enabled by the user. No passwords or keys are stored in the repo.
- Default network exposure: server loopback only; future LAN/authentication choice remains open.
- Future reconciliation should consider stale edit conflicts if multiple people edit simultaneously.
  V1 absolute reconciliation uses the quantity at commit time and returns actual before/after.
- Backups retain 30 most recent successful snapshots; no off-server protection yet.

- Phase 2: read-only Open Food Facts v3 enrichment with permanent successful cache, retry cooldowns,
  persistent provider rate budget, and manual-data precedence. Schema v2 preserves v1 data.
- No image downloads or nutrition/recipe calculation yet; full source product payload is retained locally.

- Phase 3: responsive framework-free browser UI served by FastAPI, with no external asset dependencies.
- Browser count corrections require review/confirmation, a same-tab persistent retry ID, and an
  optional expected_quantity check to reject stale counts. Metadata edits remain last-writer-wins.
- Household/LAN access and authentication remain deferred; the service stays bound to loopback.

- The household owner subsequently approved trusted LAN access without login. Deployment adds a
  specific LAN IPv4 binding using an ignored override and .env while retaining loopback access.
- No router/firewall settings changed; request IDs support plain HTTP through cryptographic UUID fallback.

- Firmware prototype: common resistive CYD ILI9341 + XPT2046 profile, pinned PlatformIO dependencies,
  diagnostics as the default first-flash target, separate manual-barcode inventory terminal.
- Bluetooth scanner compatibility and physical display/touch/Wi-Fi validation remain pending.
- Compile-only verification on Debian does not access USB; upload/serial work stays on Windows.

- Scanner arrival: Bluetooth Classic/SPP master connects to NETUM by configured name or exact MAC.
- Continuous ADD/REMOVE uses a persisted eight-request FIFO and background HTTP worker. Scanner test
  performs no inventory/API writes. Error/overflow recovery requires resuming and rescanning rejected items.
- New Bluetooth builds use huge_app with unchanged NVS location; old pending records load safely.
- Physical pairing and rapid-scan/outage acceptance remain to be verified with the household scanner.
