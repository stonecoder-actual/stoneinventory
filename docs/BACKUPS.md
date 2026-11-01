# Backups and restoration

The dedicated backup container takes an online SQLite backup at startup and every 24 hours.
It checks integrity, atomically publishes the completed file, and retains the newest 30 snapshots.
Timestamps are UTC. Backups are under YOUR_PROJECT_DIRECTORY/backups, separate from data/.
The source connection is read-only. The data directory is writable so SQLite can coordinate WAL/SHM files safely. Failures appear in backup service logs;
there is no external alerting yet. Restarting the backup service triggers another snapshot.

Manual snapshot:
```sh
docker compose run --rm --no-deps backup python -m app.backup
```

Restore, on Debian in YOUR_PROJECT_DIRECTORY:
1. Stop both services with docker compose down.
2. Choose a specific timestamped backup and verify it with Python sqlite3 PRAGMA integrity_check.
3. Move the entire data directory to a uniquely named safety directory (retain it; do not delete it).
4. Create a new data directory owned by sam.
5. Copy the chosen snapshot to data/inventory.sqlite3, owned by sam.
6. Start with docker compose up -d; verify health, known counts, and transaction history.

Do not mix a restored database with WAL/SHM files from a different database.
The automated test restores a snapshot and checks both quantity and audit history.
A live HTTP validation also confirms a restored snapshot against the running test operations.
Source files belong in private GitHub version control; databases, .env, and backups are excluded.
Local backups remain vulnerable to server/disk loss. Off-server storage is a required follow-up.
OneDrive or Google Drive integration is not configured.
