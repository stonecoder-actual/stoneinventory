"""Consistent snapshots; run as a dedicated Compose service or one-shot CLI."""
import argparse
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def backup(source, destination, retention=30):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise RuntimeError("Database does not exist; refusing an empty backup")
    if destination == source.parent:
        raise ValueError("Backup directory must differ from the database directory")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'inventory-{stamp}.sqlite3'
    temporary = target.with_suffix('.partial')
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(temporary) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed')
        temporary.replace(target)
        for old in sorted(destination.glob('inventory-*.sqlite3'), reverse=True)[retention:]:
            old.unlink()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f'event=backup_success path={target}', flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    while True:
        try:
            backup(os.environ.get('DATABASE_PATH', 'data/inventory.sqlite3'), os.environ.get('BACKUP_DIR', 'backups'))
        except Exception as exc:
            print(f'event=backup_failure error={exc}', flush=True)
            if not args.loop:
                raise
        if not args.loop:
            break
        time.sleep(86400)
