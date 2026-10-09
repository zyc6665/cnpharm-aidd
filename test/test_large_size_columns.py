"""持久化文件和镜像大小字段的范围测试。"""

from sqlalchemy import BigInteger

from app.models.artifacts import ArtifactVersion
from app.models.files import File
from app.models.image_assets import ImageAsset, ImageImport


def test_persisted_size_columns_use_big_integer() -> None:
    columns = (
        File.__table__.c.size_bytes,
        ArtifactVersion.__table__.c.size_bytes,
        ImageImport.__table__.c.size_bytes,
        ImageAsset.__table__.c.archive_size_bytes,
    )

    assert all(isinstance(column.type, BigInteger) for column in columns)
