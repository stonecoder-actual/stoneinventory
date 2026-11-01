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
