#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


OUTPUT_DIR = Path("/workspace/output")
INPUT_DIR = Path("/workspace/input")
INPUT_MANIFEST = INPUT_DIR / "manifest.json"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def main() -> int:
    task_id = os.getenv("SCIMINER_TASK_ID", "local-smoke")
    attempt_id = os.getenv("SCIMINER_ATTEMPT_ID", "local-attempt")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    inputs = stage_inputs()
    report_path = OUTPUT_DIR / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "source_task_id": task_id,
                "attempt_id": attempt_id,
                "status": "succeeded",
                "message": "Kubernetes smoke image completed",
                "inputs": inputs,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    result_path = write_result(task_id, attempt_id, report_path)
    upload_outputs(result_path)
    print(result_path.read_text(encoding="utf-8"), end="")
    return 0


def stage_inputs() -> list[dict[str, str]]:
    raw = os.getenv("SCIMINER_INPUTS_JSON", "[]")
    try:
        descriptors = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SCIMINER_INPUTS_JSON is not valid JSON") from exc
    if not isinstance(descriptors, list):
        raise RuntimeError("SCIMINER_INPUTS_JSON must be a list")

    storage = build_storage_client()
    staged: list[dict[str, str]] = []
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise RuntimeError("each input descriptor must be an object")
        name = safe_segment(descriptor.get("name"), "input name")
        uri = safe_object_key(descriptor.get("uri"))
        expected_sha = str(descriptor.get("sha256") or "").lower()
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
            raise RuntimeError(f"invalid input checksum for {name}")

        filename = safe_segment(posixpath.basename(uri), "input filename")
        destination = INPUT_DIR / name / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if storage is None:
            raise RuntimeError("input staging requires object-storage credentials")
        download_object(storage, uri, destination)
        actual_sha = sha256_file(destination)
        if actual_sha != expected_sha:
            raise RuntimeError(f"input checksum mismatch for {name}")
        staged.append(
            {
                "name": name,
                "uri": uri,
                "sha256": actual_sha,
                "path": destination.relative_to(Path("/workspace")).as_posix(),
            }
        )

    INPUT_MANIFEST.write_text(json.dumps(staged, separators=(",", ":")), encoding="utf-8")
    return staged


def write_result(task_id: str, attempt_id: str, report_path: Path) -> Path:
    report_sha = sha256_file(report_path)
    result_path = OUTPUT_DIR / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "result_version": "aidd.sciminer/result",
                "artifacts": {
                    "report": {
                        "type": "run_report@1",
                        "files": {
                            "report_json": {
                                "path": "report.json",
                                "sha256": report_sha,
                                "content_type": "application/json",
                            }
                        },
                        "metadata": {
                            "source_task_id": task_id,
                            "attempt_id": attempt_id,
                        },
                    }
                },
                "summary": {"status": "succeeded"},
                "metrics": {"smoke": True},
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return result_path


def build_storage_client():
    values = {
        "endpoint": os.getenv("SCIMINER_OBJECT_STORAGE_ENDPOINT"),
        "bucket": os.getenv("SCIMINER_OBJECT_STORAGE_BUCKET"),
        "access_key": os.getenv("SCIMINER_OBJECT_STORAGE_ACCESS_KEY"),
        "secret_key": os.getenv("SCIMINER_OBJECT_STORAGE_SECRET_KEY"),
    }
    configured = [bool(value) for value in values.values()]
    if not any(configured):
        return None
    if not all(configured):
        raise RuntimeError("object-storage configuration must be complete")
    from minio import Minio

    endpoint = str(values["endpoint"])
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    if not parsed.hostname:
        raise RuntimeError("SCIMINER_OBJECT_STORAGE_ENDPOINT has no host")
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return Minio(
        host,
        access_key=str(values["access_key"]),
        secret_key=str(values["secret_key"]),
        secure=parsed.scheme == "https",
    )


def upload_outputs(result_path: Path) -> None:
    storage = build_storage_client()
    if storage is None:
        if os.getenv("SCIMINER_INPUTS_JSON", "[]") != "[]":
            raise RuntimeError("object-storage credentials are required when inputs are configured")
        return

    bucket = require_env("SCIMINER_OBJECT_STORAGE_BUCKET")
    prefix = safe_prefix(require_env("SCIMINER_EXECUTION_OUTPUT_PREFIX"))
    for path in sorted(OUTPUT_DIR.rglob("*")):
        if not path.is_file() or path == result_path:
            continue
        upload_file(storage, bucket, f"{prefix}/{path.relative_to(OUTPUT_DIR).as_posix()}", path)
    upload_file(storage, bucket, f"{prefix}/result.json", result_path)


def download_object(storage, key: str, destination: Path) -> None:
    bucket = require_env("SCIMINER_OBJECT_STORAGE_BUCKET")
    response = storage.get_object(bucket, key)
    try:
        with destination.open("wb") as handle:
            for chunk in response.stream(1024 * 1024):
                handle.write(chunk)
    finally:
        response.close()
        response.release_conn()


def upload_file(storage, bucket: str, key: str, path: Path) -> None:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        storage.put_object(
            bucket,
            key,
            handle,
            path.stat().st_size,
            content_type=content_type,
        )


def safe_object_key(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        raise RuntimeError("input uri must be an object key, not a URL")
    parts = raw.strip("/").split("/")
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise RuntimeError(f"unsafe input object key: {raw}")
    if any(not SAFE_SEGMENT.fullmatch(part) for part in parts):
        raise RuntimeError(f"unsafe input object key: {raw}")
    return "/".join(parts)


def safe_prefix(value: str) -> str:
    return safe_object_key(value)


def safe_segment(value: object, label: str) -> str:
    raw = str(value or "")
    if not SAFE_SEGMENT.fullmatch(raw) or raw in {".", ".."}:
        raise RuntimeError(f"unsafe {label}: {raw}")
    return raw


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"missing environment variable: {name}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"sciminer smoke runner failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
