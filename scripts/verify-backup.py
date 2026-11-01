"""Restore a snapshot to an isolated temporary directory; leave live data untouched."""
import json
import shutil
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

snapshot = max(Path("backups").glob("inventory-*.sqlite3"))
with tempfile.TemporaryDirectory(prefix="stoneinventory-restore-") as folder:
    restored = Path(folder) / "restored.sqlite3"
    shutil.copy2(snapshot, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        saved = db.execute("SELECT quantity FROM inventory WHERE barcode='0000000000000'").fetchone()[0]
        count = db.execute("SELECT count(*) FROM transactions WHERE barcode='0000000000000'").fetchone()[0]
    with urllib.request.urlopen("http://127.0.0.1:8765/api/products/0000000000000", timeout=10) as response:
        current = json.load(response)["quantity"]
    assert saved == current == 0
    assert count >= 6
print(f"Restoration verified: {snapshot.name}, quantity={saved}, history_rows={count}")
