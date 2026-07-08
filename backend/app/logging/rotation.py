# backend/app/logging/rotation.py
"""日志轮转配置模块

根据详细设计说明书 9.2 节实现。
负责日志文件的轮转策略配置。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import gzip
import logging
import logging.handlers
import os
import shutil
import time
from app.common.time import utcfromtimestamp, utcnow

logger = logging.getLogger(__name__)


class RotationType(str, Enum):
    """轮转类型"""
    SIZE = "size"           # 按大小轮转
    TIME = "time"           # 按时间轮转
    SIZE_TIME = "size_time" # 大小和时间结合


class TimeInterval(str, Enum):
    """时间间隔"""
    SECOND = "S"
    MINUTE = "M"
    HOUR = "H"
    DAY = "D"
    MIDNIGHT = "midnight"
    WEEKLY = "W0"           # 每周一


@dataclass
class SizeRotationConfig:
    """按大小轮转配置"""
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class TimeRotationConfig:
    """按时间轮转配置"""
    when: TimeInterval = TimeInterval.MIDNIGHT
    interval: int = 1
    backup_count: int = 30


@dataclass
class LogRotationConfig:
    """日志轮转配置"""
    rotation_type: RotationType = RotationType.SIZE
    size_config: SizeRotationConfig = field(default_factory=SizeRotationConfig)
    time_config: TimeRotationConfig = field(default_factory=TimeRotationConfig)
    compress: bool = True                   # 是否压缩旧日志
    compress_delay: int = 1                 # 延迟压缩（轮转后N个文件才压缩）
    encoding: str = "utf-8"
    log_dir: str = "logs"
    file_prefix: str = "sciminer"


# 预定义的轮转配置
SIZE_ROTATION = SizeRotationConfig(
    max_bytes=50 * 1024 * 1024,  # 50MB
    backup_count=10
)

TIME_ROTATION = TimeRotationConfig(
    when=TimeInterval.MIDNIGHT,
    interval=1,
    backup_count=30  # 保留30天
)

HOURLY_ROTATION = TimeRotationConfig(
    when=TimeInterval.HOUR,
    interval=1,
    backup_count=24 * 7  # 保留一周的小时日志
)


class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """带压缩功能的轮转文件处理器

    在轮转时自动压缩旧日志文件。
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: str = None,
        delay: bool = False,
        compress: bool = True,
        compress_delay: int = 1
    ):
        super().__init__(
            filename, mode, maxBytes, backupCount, encoding, delay
        )
        self.compress = compress
        self.compress_delay = compress_delay

    def doRollover(self):
        """执行轮转"""
        if self.stream:
            self.stream.close()
            self.stream = None

        if self.backupCount > 0:
            # 压缩旧文件
            if self.compress:
                for i in range(self.backupCount - 1, self.compress_delay - 1, -1):
                    sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                    dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")
                    if os.path.exists(sfn):
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        # 压缩文件
                        if not sfn.endswith(".gz"):
                            self._compress_file(sfn, dfn + ".gz")
                            os.remove(sfn)
                        else:
                            os.rename(sfn, dfn)

            # 处理未压缩的最近文件
            for i in range(self.compress_delay - 1, 0, -1):
                sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)

            dfn = self.rotation_filename(f"{self.baseFilename}.1")
            if os.path.exists(dfn):
                os.remove(dfn)
            self.rotate(self.baseFilename, dfn)

        if not self.delay:
            self.stream = self._open()

    def _compress_file(self, src: str, dst: str) -> None:
        """压缩文件

        Args:
            src: 源文件路径
            dst: 目标文件路径
        """
        try:
            with open(src, "rb") as f_in:
                with gzip.open(dst, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.debug(f"Compressed log file: {src} -> {dst}")
        except Exception as e:
            logger.error(f"Failed to compress {src}: {e}")


class CompressedTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """带压缩功能的时间轮转处理器

    在轮转时自动压缩旧日志文件。
    """

    def __init__(
        self,
        filename: str,
        when: str = "h",
        interval: int = 1,
        backupCount: int = 0,
        encoding: str = None,
        delay: bool = False,
        utc: bool = False,
        atTime: datetime = None,
        compress: bool = True
    ):
        super().__init__(
            filename, when, interval, backupCount, encoding, delay, utc, atTime
        )
        self.compress = compress

    def doRollover(self):
        """执行轮转"""
        if self.stream:
            self.stream.close()
            self.stream = None

        # 获取当前时间和轮转时间
        currentTime = int(time.time())
        dstNow = time.localtime(currentTime)[-1]
        t = self.rolloverAt - self.interval

        if self.utc:
            timeTuple = time.gmtime(t)
        else:
            timeTuple = time.localtime(t)
            dstThen = timeTuple[-1]
            if dstNow != dstThen:
                if dstNow:
                    addend = 3600
                else:
                    addend = -3600
                timeTuple = time.localtime(t + addend)

        # 生成轮转文件名
        dfn = self.rotation_filename(
            self.baseFilename + "." + time.strftime(self.suffix, timeTuple)
        )

        if os.path.exists(dfn):
            os.remove(dfn)

        self.rotate(self.baseFilename, dfn)

        # 压缩文件
        if self.compress:
            self._compress_old_file(dfn)

        # 删除旧文件
        if self.backupCount > 0:
            self._delete_old_files()

        # 计算下次轮转时间
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt = newRolloverAt + self.interval
        self.rolloverAt = newRolloverAt

        if not self.delay:
            self.stream = self._open()

    def _compress_old_file(self, filepath: str) -> None:
        """压缩旧日志文件"""
        if os.path.exists(filepath) and not filepath.endswith(".gz"):
            try:
                with open(filepath, "rb") as f_in:
                    with gzip.open(filepath + ".gz", "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(filepath)
                logger.debug(f"Compressed log file: {filepath}")
            except Exception as e:
                logger.error(f"Failed to compress {filepath}: {e}")

    def _delete_old_files(self) -> None:
        """删除旧日志文件"""
        dirName, baseName = os.path.split(self.baseFilename)
        fileNames = os.listdir(dirName) if dirName else os.listdir(".")
        prefix = baseName + "."
        plen = len(prefix)

        # 收集匹配的文件
        matching = []
        for fileName in fileNames:
            if fileName.startswith(prefix):
                suffix = fileName[plen:]
                # 处理.gz后缀
                if suffix.endswith(".gz"):
                    suffix = suffix[:-3]
                if self.extMatch.match(suffix):
                    matching.append(os.path.join(dirName, fileName) if dirName else fileName)

        matching.sort()

        # 删除超出保留数量的文件
        if len(matching) > self.backupCount:
            for s in matching[:len(matching) - self.backupCount]:
                try:
                    os.remove(s)
                    logger.debug(f"Deleted old log file: {s}")
                except Exception as e:
                    logger.error(f"Failed to delete {s}: {e}")


def create_rotating_handler(
    config: LogRotationConfig,
    log_name: str = "app"
) -> logging.Handler:
    """创建日志轮转处理器

    Args:
        config: 轮转配置
        log_name: 日志名称

    Returns:
        logging.Handler: 日志处理器
    """
    os.makedirs(config.log_dir, exist_ok=True)
    log_path = os.path.join(config.log_dir, f"{config.file_prefix}_{log_name}.log")

    if config.rotation_type == RotationType.SIZE:
        handler = CompressedRotatingFileHandler(
            filename=log_path,
            maxBytes=config.size_config.max_bytes,
            backupCount=config.size_config.backup_count,
            encoding=config.encoding,
            compress=config.compress,
            compress_delay=config.compress_delay
        )
    elif config.rotation_type == RotationType.TIME:
        handler = CompressedTimedRotatingFileHandler(
            filename=log_path,
            when=config.time_config.when.value,
            interval=config.time_config.interval,
            backupCount=config.time_config.backup_count,
            encoding=config.encoding,
            compress=config.compress
        )
    else:
        # SIZE_TIME: 使用按大小轮转作为默认
        handler = CompressedRotatingFileHandler(
            filename=log_path,
            maxBytes=config.size_config.max_bytes,
            backupCount=config.size_config.backup_count,
            encoding=config.encoding,
            compress=config.compress,
            compress_delay=config.compress_delay
        )

    return handler


def setup_log_rotation(
    logger_name: str,
    config: Optional[LogRotationConfig] = None,
    formatter: Optional[logging.Formatter] = None
) -> logging.Logger:
    """设置日志轮转

    Args:
        logger_name: 日志器名称
        config: 轮转配置
        formatter: 日志格式化器

    Returns:
        logging.Logger: 配置好的日志器
    """
    if config is None:
        config = LogRotationConfig()

    log = logging.getLogger(logger_name)
    handler = create_rotating_handler(config, logger_name)

    if formatter:
        handler.setFormatter(formatter)
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

    log.addHandler(handler)

    return log


class LogRotationManager:
    """日志轮转管理器

    统一管理所有日志文件的轮转。
    """

    def __init__(self, base_config: Optional[LogRotationConfig] = None):
        """初始化管理器

        Args:
            base_config: 基础配置
        """
        self.base_config = base_config or LogRotationConfig()
        self._handlers: Dict[str, logging.Handler] = {}

    def add_log(
        self,
        name: str,
        level: int = logging.INFO,
        config: Optional[LogRotationConfig] = None
    ) -> logging.Logger:
        """添加日志

        Args:
            name: 日志名称
            level: 日志级别
            config: 轮转配置

        Returns:
            logging.Logger: 日志器
        """
        cfg = config or self.base_config
        handler = create_rotating_handler(cfg, name)
        handler.setLevel(level)

        log = logging.getLogger(name)
        log.addHandler(handler)
        log.setLevel(level)

        self._handlers[name] = handler

        return log

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息

        Returns:
            Dict: 统计信息
        """
        stats = {}

        for name, handler in self._handlers.items():
            if hasattr(handler, "baseFilename"):
                log_path = handler.baseFilename
                if os.path.exists(log_path):
                    stat = os.stat(log_path)
                    stats[name] = {
                        "path": log_path,
                        "size_bytes": stat.st_size,
                        "modified": utcfromtimestamp(stat.st_mtime).isoformat()
                    }

                    # 统计轮转文件
                    dir_path = os.path.dirname(log_path)
                    base_name = os.path.basename(log_path)
                    rotated_files = [
                        f for f in os.listdir(dir_path)
                        if f.startswith(base_name) and f != base_name
                    ]
                    stats[name]["rotated_count"] = len(rotated_files)

        return stats

    def force_rotate(self, name: str) -> bool:
        """强制轮转指定日志

        Args:
            name: 日志名称

        Returns:
            bool: 是否成功
        """
        handler = self._handlers.get(name)
        if handler and hasattr(handler, "doRollover"):
            try:
                handler.doRollover()
                logger.info(f"Forced rotation for log: {name}")
                return True
            except Exception as e:
                logger.error(f"Failed to rotate log {name}: {e}")
                return False
        return False

    def cleanup_old_logs(self, max_age_days: int = 30) -> int:
        """清理旧日志文件

        Args:
            max_age_days: 最大保留天数

        Returns:
            int: 清理的文件数
        """
        cleaned = 0
        cutoff = utcnow() - timedelta(days=max_age_days)

        for name, handler in self._handlers.items():
            if hasattr(handler, "baseFilename"):
                dir_path = os.path.dirname(handler.baseFilename)
                if not os.path.exists(dir_path):
                    continue

                for filename in os.listdir(dir_path):
                    file_path = os.path.join(dir_path, filename)
                    if os.path.isfile(file_path):
                        mtime = utcfromtimestamp(os.path.getmtime(file_path))
                        if mtime < cutoff:
                            try:
                                os.remove(file_path)
                                cleaned += 1
                                logger.info(f"Cleaned old log: {file_path}")
                            except Exception as e:
                                logger.error(f"Failed to clean {file_path}: {e}")

        return cleaned


# 全局轮转管理器
_rotation_manager: Optional[LogRotationManager] = None


def get_rotation_manager() -> LogRotationManager:
    """获取日志轮转管理器单例

    Returns:
        LogRotationManager: 管理器实例
    """
    global _rotation_manager
    if _rotation_manager is None:
        _rotation_manager = LogRotationManager()
    return _rotation_manager
