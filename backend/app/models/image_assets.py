"""管理员导入的容器镜像资产。"""

import enum

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class ImageImportStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImageImport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "image_imports"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    archive_sha256 = Column(String(64), nullable=False, index=True)
    requested_repository = Column(String(255), nullable=False)
    requested_tag = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default=ImageImportStatus.PENDING.value, index=True)
    error_message = Column(Text, nullable=True)

    image_asset = relationship(
        "ImageAsset",
        back_populates="image_import",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ImageAsset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "image_assets"
    __table_args__ = (
        UniqueConstraint("repository", "tag", name="uq_image_assets_repository_tag"),
    )

    import_id = Column(String(36), ForeignKey("image_imports.id"), nullable=False, unique=True, index=True)
    repository = Column(String(255), nullable=False, index=True)
    tag = Column(String(128), nullable=False)
    image_reference = Column(String(512), nullable=False)
    manifest_digest = Column(String(71), nullable=False, index=True)
    archive_sha256 = Column(String(64), nullable=False, index=True)
    archive_size_bytes = Column(BigInteger, nullable=False)
    platform = Column(String(64), nullable=False, default="linux/amd64")
    status = Column(String(32), nullable=False, default="ready", index=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    creator = relationship("User")
    image_import = relationship("ImageImport", back_populates="image_asset")
