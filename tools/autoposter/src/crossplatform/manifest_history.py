"""Durable-on-filesystem, append-only Short v2 manifest snapshots.

This records render identity only, NOT proof of successful social publication.
The hosting job must persist this directory across runs to preserve history.
"""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def archive_render_manifest(manifest: dict[str, Any], directory: str | Path) -> Path:
    key = str(manifest.get("content_key") or "").strip()
    created = str(manifest.get("created_at") or "").strip()
    if not key or not created:
        raise ValueError("manifest needs content_key and created_at")
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    # Hash over complete content prevents different renders of the same article
    # from overwriting one another. Replaying identical output is idempotent.
    name = hashlib.sha256(encoded).hexdigest() + ".json"
    target = folder / name
    if target.exists():
        if target.read_bytes() != encoded:
            raise ValueError("archived manifest hash collision")
        return target
    fd, temp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Do not overwrite an existing snapshot. Only a local filesystem guarantee.
        if target.exists():
            if target.read_bytes() != encoded:
                raise ValueError("archived manifest conflict")
            return target
        os.replace(temp_name, target)
        return target
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_render_manifests(directory: str | Path) -> list[dict[str, Any]]:
    folder = Path(directory)
    if not folder.exists():
        return []
    result = []
    for file in sorted(folder.glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("content_key"):
            raise ValueError(f"bad archived manifest: {file}")
        result.append(data)
    return result
