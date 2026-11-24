"""Consistent SQLite online backup. Restore only into a new destination."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file() or destination.exists():
        raise ValueError('source must exist; destination must be new')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True) as original:
        with sqlite3.connect(destination) as copy:
            original.backup(copy)
            if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup integrity check failed')
    record = {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'integrity': 'ok'}
    destination.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    print(json.dumps(backup(args.source, args.destination)))
