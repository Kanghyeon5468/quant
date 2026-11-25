"""Immutable, hash-checked local observations. API processes read without credentials."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from quantcore.core.files import atomic_json


def now():
    return datetime.now(timezone.utc).isoformat()


def read_snapshot(data_directory, kind):
    directory = Path(data_directory) / "information" / kind
    pointer = directory / "latest.json"
    if not pointer.exists():
        return None
    name = json.loads(pointer.read_text())["snapshot_directory"]
    if Path(name).name != name:
        raise ValueError("unsafe information snapshot path")
    folder = directory / name
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, digest in manifest["hashes"].items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("information snapshot hash mismatch")
    return folder, manifest


def publish(data_directory, kind, documents, metadata):
    directory = Path(data_directory) / "information" / kind
    folder = directory / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    hashes = {}
    for name, value in documents.items():
        if Path(name).name != name:
            raise ValueError("unsafe information document path")
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, indent=2).encode()
        (folder / name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    manifest = {**metadata, "hashes": hashes, "snapshot_id": folder.name}
    atomic_json(folder / "manifest.json", manifest)
    atomic_json(directory / "latest.json", {"snapshot_directory": folder.name})
    return folder, manifest
