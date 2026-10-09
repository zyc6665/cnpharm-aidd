#!/usr/bin/env python3
"""迁移本地文件到 MinIO，并把 PostgreSQL 文件记录切换为对象存储。"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from botocore.client import Config
from botocore.session import get_session
from sqlalchemy import create_engine, select


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import agent, files, statistics, system_settings, tasks, tools, users, verification, workflows  # noqa: F401,E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-db",
        type=Path,
        default=BACKEND_ROOT / "storage" / "scitool.db",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=BACKEND_ROOT,
    )
    parser.add_argument(
        "--target-url",
        default=os.environ.get("TARGET_DATABASE_URL"),
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:30900"),
    )
    parser.add_argument("--access-key", default=os.environ.get("MINIO_ACCESS_KEY"))
    parser.add_argument("--secret-key", default=os.environ.get("MINIO_SECRET_KEY"))
    parser.add_argument(
        "--bucket",
        default=os.environ.get("MINIO_BUCKET", "scitool-files"),
    )
    return parser.parse_args()


class MinioObjectStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self.bucket = bucket
        self.client = get_session().create_client(
            "s3",
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except self.client.exceptions.NoSuchBucket:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, content: bytes, content_type: str | None) -> None:
        arguments = {"Bucket": self.bucket, "Key": key, "Body": content}
        if content_type:
            arguments["ContentType"] = content_type
        self.client.put_object(**arguments)


def _source_path(source_root: Path, storage_path: str) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == source_root.name:
        return source_root.parent / path
    return source_root / path


def migrate(
    source_db: Path,
    source_root: Path,
    target_url: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
) -> None:
    if not source_db.is_file():
        raise SystemExit(f"source database does not exist: {source_db}")
    if not target_url or not target_url.startswith("postgresql+"):
        raise SystemExit("TARGET_DATABASE_URL or --target-url must be PostgreSQL")
    if not access_key or not secret_key:
        raise SystemExit("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")

    source_engine = create_engine(f"sqlite:///{source_db.resolve()}")
    target_engine = create_engine(
        target_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1),
        future=True,
    )
    source_table = Base.metadata.tables["files"]
    target_table = Base.metadata.tables["files"]
    object_store = MinioObjectStore(endpoint, access_key, secret_key, bucket)
    object_store.ensure_bucket()

    with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
        rows = source_connection.execute(select(source_table)).mappings().all()
        for index, row in enumerate(rows, start=1):
            source_path = _source_path(source_root, str(row["storage_path"]))
            if not source_path.is_file():
                print(f"marked missing local file as corrupted: {row['id']}: {source_path}")
                target_connection.execute(
                    target_table.update()
                    .where(target_table.c.id == row["id"])
                    .values(
                        storage_backend="minio",
                        storage_path=f"missing/{row['id']}",
                        is_corrupted=True,
                    )
                )
                continue
            content = source_path.read_bytes()
            actual_sha = hashlib.sha256(content).hexdigest()
            if actual_sha != str(row["sha256"]).lower():
                raise ValueError(f"sha256 mismatch for {row['id']}: {source_path}")
            key = f"files/{row['id']}/{row['filename']}"
            object_store.put(key, content, row["content_type"])
            target_connection.execute(
                target_table.update()
                .where(target_table.c.id == row["id"])
                .values(storage_backend="minio", storage_path=key)
            )
            if index == 1 or index % 50 == 0 or index == len(rows):
                print(f"migrated files: {index}/{len(rows)}")

    source_engine.dispose()
    target_engine.dispose()


if __name__ == "__main__":
    arguments = _parse_args()
    migrate(
        arguments.source_db,
        arguments.source_root,
        arguments.target_url,
        arguments.endpoint,
        arguments.access_key,
        arguments.secret_key,
        arguments.bucket,
    )
