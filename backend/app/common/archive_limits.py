"""解压/归档展开的安全上限（P2 注入/存储 DoS 硬化）。

压缩归档容易承载「解压炸弹」：很小的压缩包可以展开出远超其体积的解压数据，
若不设上限，解压/展开阶段会把磁盘或内存打满。这里集中两个默认上限，供
``app.tasks.molecule_scoring``（zip 内 SDF 提取）与
``app.services.image_asset_import``（docker save / OCI tar 导入）共用：

* ``MAX_ARCHIVE_UNCOMPRESSED_BYTES``：累计解压/展开字节上限，默认 200 MiB；
* ``MAX_ARCHIVE_ENTRIES``：归档条目数上限，默认 10000。

部署侧可通过同名环境变量（经 ``settings``）覆盖；``config.py`` 未声明时回退默认值。
"""

from __future__ import annotations

from app.config import settings

#: 累计解压/展开字节上限，默认 200 MiB。
MAX_ARCHIVE_UNCOMPRESSED_BYTES = int(
    getattr(settings, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 200 * 1024 * 1024)
)

#: 归档条目数上限，默认 10000。
MAX_ARCHIVE_ENTRIES = int(getattr(settings, "MAX_ARCHIVE_ENTRIES", 10000))


__all__ = ["MAX_ARCHIVE_ENTRIES", "MAX_ARCHIVE_UNCOMPRESSED_BYTES"]
