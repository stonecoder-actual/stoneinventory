# Project working instructions

Read README.md and docs/DECISIONS.md before changes.
Backend commands and tests execute on Debian over SSH; ESP32 USB access is on Windows.
Keep scope to the current authorized phase. Never alter unrelated services.
Preserve existing databases and transaction history. Keep secrets and runtime state out of Git.
Mandatory request-id deduplication, atomic inventory/audit writes, and distinct RECONCILE semantics.
Run sh scripts/test.sh after backend changes. Mock external lookups when Phase 2 is added.
Verify live HTTP behavior and backup restoration before reporting deployment success.
