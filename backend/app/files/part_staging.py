"""分片暂存抽象（docs/04 §5.8、docs/05 §4.2）。

为什么需要这层抽象
------------------
分片上传的中间字节必须有地方放，而「放哪里」取决于部署形态：

* 开发/单机：落本地磁盘，路径 ``{STORAGE_PATH}/_uploads/{session_id}/{part:05d}.part``；
* 生产：``STORAGE_BACKEND`` 被强制为 ``minio``（``app.config`` 有硬校验），
  backend 容器**不挂卷**，多个副本还在不同节点上——分片如果写本地盘，
  进程一重启就丢、换副本就找不到，断点续传彻底失效。

因此暂存位置必须跟 ``StorageBackend`` 走同一套配置，而不是固定写本地盘。

与「MinIO Multipart Upload」的关系
----------------------------------
本模块实现的是**对象级分片暂存**：每片是对象存储里的一个独立临时对象
（``_uploads/{session_id}/{part:05d}.part``），合并时按序读回拼装。它不是
S3/MinIO 的原生 Multipart Upload（那个要把所有片挂在同一个 ``upload_id`` 下，
且只能用 SDK 的私有方法 ``_create_multipart_upload`` / ``_upload_part`` 驱动）。
选对象级方案的理由：

1. 只用 ``StorageBackend`` 的公开四方法（upload/download/delete/exists），
   不绑定某个 SDK 的私有 API；
2. 合并上限（``UPLOAD_MAX_ASSEMBLY_BYTES``）本来就要求服务端能把所有片读一遍，
   对象级方案与它同一量级，不额外增加约束；
3. 断点续传语义更简单：每片是否已收到就是对象是否存在，不需要回查 upload_id。

原生 Multipart 直传（浏览器直传对象存储、平台只做签名）仍是后续优化项，
已经写进 ``docs/17-交付仓库与分支策略.md`` §5.7 的未落地清单。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import AsyncIterator, Protocol

import aiofiles

from app.config import settings
from app.storage.factory import get_storage_backend

#: 暂存对象/目录的逻辑前缀；本地后端下就是 ``{STORAGE_PATH}/_uploads``。
SCRATCH_PREFIX = "_uploads"


def _part_name(part_number: int) -> str:
    return f"{int(part_number):05d}.part"


def scratch_object_key(session_id: str, part_number: int) -> str:
    """对象存储中的分片键。"""
    return f"{SCRATCH_PREFIX}/{session_id}/{_part_name(part_number)}"


class PartStaging(Protocol):
    """分片暂存的后端无关接口。

    所有方法都以 ``session_id`` + ``part_number`` 定位，调用方不需要知道字节
    最终落在本地盘还是对象存储。
    """

    async def write_part(self, session_id: str, part_number: int, content: bytes) -> int:
        """写入一片，返回写入字节数。"""

    async def write_part_stream(
        self,
        session_id: str,
        part_number: int,
        chunks: AsyncIterator[bytes],
    ) -> int:
        """流式写入一片，返回写入字节数。

        与 ``write_part`` 的区别是不把整段字节驻留内存：调用方按块喂入，实现方
        边收边落盘/上传。用于 P2 分片大小上限硬化（单分片不得整段 ``Body`` 读入）。
        """

    async def read_part(self, session_id: str, part_number: int) -> bytes:
        """读回一片的字节。"""

    async def part_size(self, session_id: str, part_number: int) -> int | None:
        """片大小；不存在返回 ``None``（不做异常控制流）。"""

    async def discard(self, session_id: str) -> None:
        """删除整个会话的所有暂存分片；失败不抛错。"""


class LocalPartStaging:
    """本地磁盘暂存（开发/单机部署）。"""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = Path(base_path or settings.STORAGE_PATH)

    def directory(self, session_id: str) -> Path:
        return self.base_path / SCRATCH_PREFIX / str(session_id)

    def part_path(self, session_id: str, part_number: int) -> Path:
        return self.directory(session_id) / _part_name(part_number)

    async def write_part(self, session_id: str, part_number: int, content: bytes) -> int:
        path = self.part_path(session_id, part_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return len(content)

    async def write_part_stream(
        self,
        session_id: str,
        part_number: int,
        chunks: AsyncIterator[bytes],
    ) -> int:
        path = self.part_path(session_id, part_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 先写同目录临时文件再 ``os.replace``，避免半截分片被合并流程读到。
        temp_path = path.with_name(path.name + ".streaming")
        written = 0
        try:
            async with aiofiles.open(temp_path, "wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    await handle.write(chunk)
                    written += len(chunk)
            os.replace(temp_path, path)
        except BaseException:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return written

    async def read_part(self, session_id: str, part_number: int) -> bytes:
        path = self.part_path(session_id, part_number)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_bytes()

    async def part_size(self, session_id: str, part_number: int) -> int | None:
        path = self.part_path(session_id, part_number)
        if not path.exists():
            return None
        return path.stat().st_size

    async def discard(self, session_id: str) -> None:
        import shutil

        shutil.rmtree(self.directory(session_id), ignore_errors=True)


class ObjectPartStaging:
    """对象存储暂存（生产部署，backend 容器无持久卷）。"""

    def __init__(self, backend_type: str | None = None) -> None:
        self._backend_type = backend_type or settings.STORAGE_BACKEND

    def _backend(self):
        return get_storage_backend(self._backend_type)  # type: ignore[arg-type]

    async def write_part(self, session_id: str, part_number: int, content: bytes) -> int:
        await self._backend().upload(
            content,
            scratch_object_key(session_id, part_number),
            "application/octet-stream",
        )
        return len(content)

    async def write_part_stream(
        self,
        session_id: str,
        part_number: int,
        chunks: AsyncIterator[bytes],
    ) -> int:
        key = scratch_object_key(session_id, part_number)
        written = 0
        temp_path: str | None = None
        try:
            # 先落本地临时文件收集全部块，再用后端 ``upload_stream`` 一次上传：
            # 对象存储的 put_object 需要已知总大小，而请求流是分块到达的。
            with tempfile.NamedTemporaryFile(delete=False) as spool:
                temp_path = spool.name
                async for chunk in chunks:
                    if not chunk:
                        continue
                    spool.write(chunk)
                    written += len(chunk)
                spool.flush()
            with open(temp_path, "rb") as handle:
                await self._backend().upload_stream(
                    handle, key, written, "application/octet-stream"
                )
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        return written

    async def read_part(self, session_id: str, part_number: int) -> bytes:
        return await self._backend().download(
            scratch_object_key(session_id, part_number)
        )

    async def part_size(self, session_id: str, part_number: int) -> int | None:
        info = await self._backend().get_info(
            scratch_object_key(session_id, part_number)
        )
        return None if info is None else int(info.size)

    async def discard(self, session_id: str) -> None:
        # 对象存储没有「删前缀」，只能先列再删。这里按已知片数上限（128）枚举，
        # 比列桶便宜得多，也不依赖 bucket 的 list 权限。
        backend = self._backend()
        for number in range(1, 129):
            try:
                await backend.delete(scratch_object_key(session_id, number))
            except Exception:  # noqa: BLE001 - 清理是尽力而为，失败不影响业务结果
                continue


def build_part_staging() -> PartStaging:
    """按 ``STORAGE_BACKEND`` 选暂存实现。

    这是 B3 的修复点：分片不再无条件写本地盘。生产强制 ``minio`` 时，
    分片直接进对象存储的 ``_uploads/`` 前缀，重启与多副本都不丢。
    """
    if settings.STORAGE_BACKEND == "minio":
        return ObjectPartStaging()
    return LocalPartStaging()


__all__ = [
    "SCRATCH_PREFIX",
    "LocalPartStaging",
    "ObjectPartStaging",
    "PartStaging",
    "build_part_staging",
    "scratch_object_key",
]
