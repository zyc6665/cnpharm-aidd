"""文件记录通用规则测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.files.file_records import (  # noqa: E402
    delete_stored_content,
    delete_stored_file,
    file_storage_path,
    read_stored_content,
    user_can_access_file,
    user_can_manage_file,
)


def test_file_storage_path_prefers_persisted_storage_path(tmp_path) -> None:
    file_path = tmp_path / "stored.pdb"
    file_record = SimpleNamespace(
        id="file-1",
        filename="fallback.pdb",
        storage_path=str(file_path),
    )

    assert file_storage_path(file_record) == file_path


def test_file_storage_path_falls_back_to_file_id_and_filename(
    monkeypatch,
    tmp_path,
) -> None:
    expected = tmp_path / "file-1_input.pdb"
    monkeypatch.setattr(
        "app.files.file_records.get_file_path",
        lambda file_id, filename: expected,
    )
    file_record = SimpleNamespace(
        id="file-1",
        filename="input.pdb",
        storage_path=None,
    )

    assert file_storage_path(file_record) == expected


def test_file_access_rules_allow_public_owner_and_admin() -> None:
    public_file = SimpleNamespace(is_public=True, owner_id="owner")
    private_file = SimpleNamespace(is_public=False, owner_id="owner")
    owner = SimpleNamespace(id="owner", role="user")
    admin = SimpleNamespace(id="admin", role="admin")
    stranger = SimpleNamespace(id="stranger", role="user")

    assert user_can_access_file(public_file, None) is True
    assert user_can_access_file(private_file, owner) is True
    assert user_can_access_file(private_file, admin) is True
    assert user_can_access_file(private_file, stranger) is False
    assert user_can_access_file(private_file, None) is False


def test_file_manage_rules_allow_only_owner_or_admin() -> None:
    file_record = SimpleNamespace(is_public=True, owner_id="owner")
    owner = SimpleNamespace(id="owner", role="user")
    admin = SimpleNamespace(id="admin", role="admin")
    stranger = SimpleNamespace(id="stranger", role="user")

    assert user_can_manage_file(file_record, owner) is True
    assert user_can_manage_file(file_record, admin) is True
    assert user_can_manage_file(file_record, stranger) is False
    assert user_can_manage_file(file_record, None) is False


def test_delete_stored_file_unlinks_existing_file(tmp_path) -> None:
    file_path = tmp_path / "stored.pdb"
    file_path.write_text("ATOM\n", encoding="utf-8")
    file_record = SimpleNamespace(
        id="file-1",
        filename="stored.pdb",
        storage_path=str(file_path),
    )

    delete_stored_file(file_record)

    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_stored_content_uses_recorded_minio_backend(monkeypatch) -> None:
    deleted_paths: list[str] = []

    class FakeStorage:
        async def delete(self, path: str) -> bool:
            deleted_paths.append(path)
            return True

    monkeypatch.setattr(
        "app.storage.factory.get_storage_backend",
        lambda backend: FakeStorage(),
    )

    await delete_stored_content(
        SimpleNamespace(storage_backend="minio", storage_path="files/input.pdb")
    )

    assert deleted_paths == ["files/input.pdb"]


@pytest.mark.asyncio
async def test_read_stored_content_uses_injected_configured_backend() -> None:
    class FakeStorage:
        async def download(self, path: str) -> bytes:
            assert path == "/tmp/input.pdb"
            return b"ATOM\n"

    content = await read_stored_content(
        SimpleNamespace(storage_backend="local", storage_path="/tmp/input.pdb"),
        FakeStorage(),
    )

    assert content == b"ATOM\n"
