"""
文件处理模块

处理文件上传、下载、临时文件管理等功能
"""

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO, Optional, Tuple, Union

import aiofiles
import aiohttp
from fastapi import UploadFile

from app.config import settings
from app.core.errors import ErrorCode, FileError, ValidationError

logger = logging.getLogger(__name__)


class FileHandler:
    """文件处理器"""

    # 支持的输入格式及其 MIME 类型
    INPUT_FORMATS = {
        "pdb": {
            "extensions": [".pdb"],
            "mime_types": ["chemical/x-pdb", "application/octet-stream"],
        },
        "mol2": {
            "extensions": [".mol2"],
            "mime_types": ["chemical/x-mol2", "application/octet-stream"],
        },
    }

    def __init__(self, temp_dir: Optional[str] = None, output_dir: Optional[str] = None):
        """
        初始化文件处理器

        Args:
            temp_dir: 临时文件目录
            output_dir: 输出文件目录
        """
        self.temp_dir = Path(temp_dir or settings.TEMP_DIR)
        self.output_dir = Path(output_dir or settings.OUTPUT_DIR)
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要目录存在"""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_file_format(filename: str) -> Optional[str]:
        """
        从文件名获取格式

        Args:
            filename: 文件名

        Returns:
            格式名称（pdb/mol2）或 None
        """
        ext = Path(filename).suffix.lower()
        for fmt, info in FileHandler.INPUT_FORMATS.items():
            if ext in info["extensions"]:
                return fmt
        return None

    @staticmethod
    def validate_file_format(filename: str) -> str:
        """
        验证文件格式

        Args:
            filename: 文件名

        Returns:
            格式名称

        Raises:
            ValidationError: 格式不支持
        """
        fmt = FileHandler.get_file_format(filename)
        if fmt is None:
            ext = Path(filename).suffix
            raise ValidationError(
                message=f"Invalid input file format: {ext}",
                code=ErrorCode.INVALID_INPUT_FORMAT,
                details={
                    "received_format": ext,
                    "supported_formats": list(FileHandler.INPUT_FORMATS.keys()),
                    "suggestion": "Please provide a PDB or MOL2 format protein structure file",
                },
            )
        return fmt

    def validate_file_size(self, size: int, filename: str = ""):
        """
        验证文件大小

        Args:
            size: 文件大小（字节）
            filename: 文件名（用于错误信息）

        Raises:
            ValidationError: 文件过大
        """
        if size > settings.MAX_FILE_SIZE:
            raise ValidationError(
                message=f"File size exceeds limit: {size} bytes",
                code=ErrorCode.FILE_SIZE_EXCEEDED,
                details={
                    "file": filename,
                    "size": size,
                    "max_size": settings.MAX_FILE_SIZE,
                    "max_size_mb": settings.MAX_FILE_SIZE // (1024 * 1024),
                },
            )

    def create_temp_path(self, suffix: str = "") -> Path:
        """
        创建临时文件路径

        Args:
            suffix: 文件后缀

        Returns:
            临时文件路径
        """
        filename = f"{uuid.uuid4().hex}{suffix}"
        return self.temp_dir / filename

    def create_output_path(self, task_id: str, filename: str) -> Path:
        """
        创建输出文件路径

        Args:
            task_id: 任务 ID
            filename: 文件名

        Returns:
            输出文件路径
        """
        task_dir = self.output_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir / filename

    async def save_upload_file(self, file: UploadFile) -> Tuple[Path, str]:
        """
        保存上传的文件

        Args:
            file: FastAPI UploadFile 对象

        Returns:
            (文件路径, 文件格式)

        Raises:
            ValidationError: 格式或大小不合法
            FileError: 保存失败
        """
        # 验证格式
        filename = file.filename or "unknown"
        fmt = self.validate_file_format(filename)

        # 读取内容
        content = await file.read()

        # 验证大小
        self.validate_file_size(len(content), filename)

        # 保存到临时文件
        suffix = Path(filename).suffix
        temp_path = self.create_temp_path(suffix)

        try:
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(content)
            logger.info(f"已保存上传文件: {temp_path}")
            return temp_path, fmt
        except Exception as e:
            logger.error(f"保存上传文件失败: {e}")
            raise FileError(
                message=f"Failed to save uploaded file: {e}",
                code=ErrorCode.FILE_STORAGE_FAILED,
            )

    async def download_file(self, url: str) -> Tuple[Path, str]:
        """
        从 URL 下载文件

        Args:
            url: 文件 URL

        Returns:
            (文件路径, 文件格式)

        Raises:
            ValidationError: 格式不支持
            FileError: 下载失败
        """
        # 从 URL 提取文件名
        filename = url.split("/")[-1].split("?")[0]
        fmt = self.validate_file_format(filename)

        suffix = Path(filename).suffix
        temp_path = self.create_temp_path(suffix)

        try:
            timeout = aiohttp.ClientTimeout(total=settings.DOWNLOAD_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise FileError(
                            message=f"Failed to download file: HTTP {response.status}",
                            code=ErrorCode.INPUT_FILE_NOT_FOUND,
                            details={"url": url, "status": response.status},
                        )

                    # 检查内容长度
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        self.validate_file_size(int(content_length), filename)

                    # 流式下载
                    total_size = 0
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            total_size += len(chunk)
                            if total_size > settings.MAX_FILE_SIZE:
                                # 删除部分下载的文件
                                await self.cleanup_file(temp_path)
                                raise ValidationError(
                                    message="Downloaded file exceeds size limit",
                                    code=ErrorCode.FILE_SIZE_EXCEEDED,
                                    details={
                                        "url": url,
                                        "downloaded": total_size,
                                        "max_size": settings.MAX_FILE_SIZE,
                                    },
                                )
                            await f.write(chunk)

            logger.info(f"已下载文件: {url} -> {temp_path}")
            return temp_path, fmt

        except aiohttp.ClientError as e:
            logger.error(f"下载文件失败: {url}, {e}")
            raise FileError(
                message=f"Failed to download file: {e}",
                code=ErrorCode.INPUT_FILE_NOT_FOUND,
                details={"url": url, "error": str(e)},
            )

    async def cleanup_file(self, path: Path):
        """
        清理单个文件

        Args:
            path: 文件路径
        """
        try:
            if path.exists():
                path.unlink()
                logger.debug(f"已删除文件: {path}")
        except Exception as e:
            logger.warning(f"删除文件失败: {path}, {e}")

    async def cleanup_temp_files(self, max_age_hours: int = 24):
        """
        清理过期的临时文件

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        import time

        now = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned = 0

        try:
            for item in self.temp_dir.iterdir():
                if item.is_file():
                    age = now - item.stat().st_mtime
                    if age > max_age_seconds:
                        item.unlink()
                        cleaned += 1

            if cleaned > 0:
                logger.info(f"已清理 {cleaned} 个过期临时文件")

        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    def read_file_content(self, path: Path) -> str:
        """
        读取文件内容（同步）

        Args:
            path: 文件路径

        Returns:
            文件内容字符串
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            with open(path, "r", encoding="latin-1") as f:
                return f.read()

    async def read_file_content_async(self, path: Path) -> str:
        """
        读取文件内容（异步）

        Args:
            path: 文件路径

        Returns:
            文件内容字符串
        """
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return await f.read()
        except UnicodeDecodeError:
            async with aiofiles.open(path, "r", encoding="latin-1") as f:
                return await f.read()

    async def write_file_content(self, path: Path, content: Union[str, bytes]):
        """
        写入文件内容

        Args:
            path: 文件路径
            content: 文件内容
        """
        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        async with aiofiles.open(path, mode, encoding=encoding) as f:
            await f.write(content)

    def get_file_hash(self, path: Path) -> str:
        """
        计算文件 MD5 哈希

        Args:
            path: 文件路径

        Returns:
            MD5 哈希字符串
        """
        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()


# 全局文件处理器实例
file_handler = FileHandler()


def get_file_handler() -> FileHandler:
    """获取文件处理器依赖"""
    return file_handler
