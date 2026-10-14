"""Canonical digests for persisted Tool Package manifests."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def tool_package_manifest_digest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
