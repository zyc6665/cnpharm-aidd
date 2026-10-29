#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ObjectStorageError(ValueError):
    """Raised when model Job input or output storage is invalid."""


def prepare_job_inputs(
    *,
    input_dir: Path,
    params_path: Path,
    env: dict[str, str] | None = None,
    storage: Any | None = None,
    bucket: str | None = None,
) -> list[dict[str, str]]:
    """Stage verified object inputs and materialize the standard request file."""
    values = env if env is not None else os.environ
    input_dir = Path(input_dir).resolve()
    params_path = Path(params_path)
    input_dir.mkdir(parents=True, exist_ok=True)
    descriptors = _input_descriptors(values.get("SCIMINER_INPUTS_JSON", "[]"))

    if descriptors:
        if storage is None or bucket is None:
            storage, bucket = _storage_from_environment(values)
        staged = stage_input_descriptors(
            input_dir=input_dir,
            descriptors=descriptors,
            storage=storage,
            bucket=bucket,
        )
    else:
        staged = []

    request_json = values.get("SCIMINER_REQUEST_JSON")
    if request_json:
        try:
            request_payload = json.loads(request_json)
        except json.JSONDecodeError as exc:
            raise ObjectStorageError("SCIMINER_REQUEST_JSON is not valid JSON") from exc
        if not isinstance(request_payload, dict):
            raise ObjectStorageError("SCIMINER_REQUEST_JSON must contain an object")
        params_path.parent.mkdir(parents=True, exist_ok=True)
        params_path.write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif not params_path.is_file():
        raise ObjectStorageError("model request file is missing")

    (input_dir / "manifest.json").write_text(
        json.dumps(staged, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return staged


def stage_input_descriptors(
    *,
    input_dir: Path,
    descriptors: list[dict[str, Any]],
    storage: Any,
    bucket: str,
) -> list[dict[str, str]]:
    """Download input objects into stable slot directories and verify SHA-256."""
    staged: list[dict[str, str]] = []
    destinations: set[Path] = set()
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise ObjectStorageError("each input descriptor must be an object")
        name = _safe_segment(descriptor.get("name"), "input name")
        object_key = _safe_object_key(descriptor.get("uri"))
        expected_sha = str(descriptor.get("sha256") or "").lower()
        if not SHA256_PATTERN.fullmatch(expected_sha):
            raise ObjectStorageError(f"invalid input checksum for {name}")

        filename = _safe_segment(PurePosixPath(object_key).name, "input filename")
        destination = Path(input_dir) / name / filename
        if destination in destinations:
            raise ObjectStorageError(f"duplicate staged input path: {name}/{filename}")
        destinations.add(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.parent.is_symlink() or destination.is_symlink():
            raise ObjectStorageError(f"staged input path must not be a symlink: {name}/{filename}")
        temporary_path = destination.with_suffix(destination.suffix + ".part")
        temporary_path.unlink(missing_ok=True)
        response = None
        completed = False
        digest = hashlib.sha256()
        try:
            response = storage.get_object(bucket, object_key)
            with temporary_path.open("wb") as handle:
                for chunk in response.stream(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
            actual_sha = digest.hexdigest()
            if actual_sha != expected_sha:
                raise ObjectStorageError(f"input checksum mismatch for {name}")
            temporary_path.replace(destination)
            completed = True
        finally:
            if not completed:
                temporary_path.unlink(missing_ok=True)
            if response is not None:
                try:
                    response.close()
                finally:
                    response.release_conn()
        staged.append(
            {
                "name": name,
                "uri": object_key,
                "sha256": actual_sha,
                "path": destination.relative_to(Path(input_dir).parent).as_posix(),
            }
        )
    return staged


def upload_output_directory(
    *,
    output_dir: Path,
    result_path: Path,
    storage: Any,
    bucket: str,
    prefix: str,
) -> list[str]:
    """Upload output files and publish result.json last as the commit marker."""
    output_dir = Path(output_dir).resolve()
    raw_result_path = Path(result_path)
    if raw_result_path.is_symlink():
        raise ObjectStorageError("result.json must not be a symlink")
    result_path = raw_result_path.resolve()
    if not result_path.is_file() or result_path.parent != output_dir:
        raise ObjectStorageError("result.json must exist directly under output_dir")

    try:
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObjectStorageError("result.json is not valid JSON") from exc
    if not isinstance(result_payload, dict) or result_payload.get("result_version") != (
        "aidd.sciminer/result"
    ):
        raise ObjectStorageError("result.json must use aidd.sciminer/result")

    normalized_prefix = _safe_object_key(prefix)
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    _verify_declared_output_files(output_dir, result_payload)

    uploaded: list[str] = []
    for path in files:
        if path == result_path:
            continue
        key = f"{normalized_prefix}/{path.relative_to(output_dir).as_posix()}"
        _upload_file(storage, bucket, key, path)
        uploaded.append(key)

    result_key = f"{normalized_prefix}/result.json"
    _upload_file(storage, bucket, result_key, result_path)
    uploaded.append(result_key)
    return uploaded


def _verify_declared_output_files(output_dir: Path, result_payload: dict[str, Any]) -> None:
    artifacts = result_payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ObjectStorageError("result.v2 artifacts must be an object")
    for value in artifacts.values():
        entries = value if isinstance(value, list) else [value]
        for artifact in entries:
            if not isinstance(artifact, dict):
                raise ObjectStorageError("result.v2 artifact entries must be objects")
            files = artifact.get("files")
            if not isinstance(files, dict):
                raise ObjectStorageError("result.v2 artifact files must be an object")
            for file_ref in files.values():
                if not isinstance(file_ref, dict):
                    raise ObjectStorageError("result.v2 file references must be objects")
                relative_path = _safe_output_path(file_ref.get("path"))
                expected_sha = str(file_ref.get("sha256") or "").lower()
                if not SHA256_PATTERN.fullmatch(expected_sha):
                    raise ObjectStorageError(f"invalid output checksum: {relative_path}")
                path = output_dir / relative_path
                resolved_path = path.resolve(strict=False)
                try:
                    resolved_path.relative_to(output_dir)
                except ValueError as exc:
                    raise ObjectStorageError(
                        f"declared output file escapes output_dir: {relative_path}"
                    ) from exc
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or resolved_path != path
                ):
                    raise ObjectStorageError(f"declared output file is missing: {relative_path}")
                if sha256_file(path) != expected_sha:
                    raise ObjectStorageError(f"output checksum mismatch: {relative_path}")


def _upload_file(storage: Any, bucket: str, key: str, path: Path) -> None:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        storage.put_object(bucket, key, handle, path.stat().st_size, content_type=content_type)


def _input_descriptors(raw: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ObjectStorageError("SCIMINER_INPUTS_JSON is not valid JSON") from exc
    if not isinstance(value, list):
        raise ObjectStorageError("SCIMINER_INPUTS_JSON must contain a list")
    return value


def _storage_from_environment(env: dict[str, str]) -> tuple[Any, str]:
    endpoint = env.get("SCIMINER_OBJECT_STORAGE_ENDPOINT")
    bucket = env.get("SCIMINER_OBJECT_STORAGE_BUCKET")
    access_key = env.get("SCIMINER_OBJECT_STORAGE_ACCESS_KEY")
    secret_key = env.get("SCIMINER_OBJECT_STORAGE_SECRET_KEY")
    if not all((endpoint, bucket, access_key, secret_key)):
        raise ObjectStorageError("object-storage configuration must be complete")

    parsed = urlparse(str(endpoint) if "://" in str(endpoint) else f"http://{endpoint}")
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ObjectStorageError("object-storage endpoint must be an HTTP(S) origin")
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    from minio import Minio

    return (
        Minio(
            host,
            access_key=str(access_key),
            secret_key=str(secret_key),
            secure=parsed.scheme == "https",
        ),
        str(bucket),
    )


def _safe_object_key(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        raise ObjectStorageError("object uri must be a key, not a URL")
    parts = raw.strip("/").split("/")
    if not parts or any(not SAFE_SEGMENT.fullmatch(part) or part in {".", ".."} for part in parts):
        raise ObjectStorageError(f"unsafe object key: {raw}")
    return "/".join(parts)


def _safe_segment(value: object, label: str) -> str:
    raw = str(value or "")
    if not SAFE_SEGMENT.fullmatch(raw) or raw in {".", ".."}:
        raise ObjectStorageError(f"unsafe {label}: {raw}")
    return raw


def _safe_output_path(value: object) -> str:
    raw = str(value or "").replace("\\", "/")
    if not raw or raw.startswith("/") or any(
        part in {"", ".", ".."} for part in raw.split("/")
    ):
        raise ObjectStorageError(f"unsafe output path: {raw}")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ObjectStorageError(f"unsafe output path: {raw}")
    return path.as_posix()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--input-dir", required=True)
    prepare_parser.add_argument("--params-json", required=True)
    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    if args.command == "prepare":
        prepare_job_inputs(
            input_dir=Path(args.input_dir),
            params_path=Path(args.params_json),
        )
        return 0

    env = dict(os.environ)
    output_dir = Path(args.output_dir).resolve()
    storage, bucket = _storage_from_environment(env)
    prefix = _safe_object_key(env.get("SCIMINER_EXECUTION_OUTPUT_PREFIX"))
    upload_output_directory(
        output_dir=output_dir,
        result_path=output_dir / "result.json",
        storage=storage,
        bucket=bucket,
        prefix=prefix,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
