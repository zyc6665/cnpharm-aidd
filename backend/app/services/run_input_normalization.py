"""Shared normalization helpers for task run inputs."""

from __future__ import annotations


def normalize_string_mapping(values: dict[str, str] | None) -> dict[str, str]:
    """Return non-empty string mappings with trimmed keys and values."""
    return {
        key: value
        for raw_key, raw_value in (values or {}).items()
        if (key := str(raw_key).strip()) and (value := str(raw_value).strip())
    }
