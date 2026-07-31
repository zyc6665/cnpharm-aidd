"""Persisted Tool Package metadata and immutable versions."""

from sqlalchemy import Boolean, Column, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class ToolPackage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tool_packages"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    current_version_id = Column(String(36), nullable=True)

    owner = relationship("User")
    versions = relationship(
        "ToolPackageVersion",
        back_populates="package",
        cascade="all, delete-orphan",
        foreign_keys="ToolPackageVersion.package_id",
    )
    current_version = relationship(
        "ToolPackageVersion",
        foreign_keys=[current_version_id],
        primaryjoin="ToolPackage.current_version_id==ToolPackageVersion.id",
        uselist=False,
        post_update=True,
    )


class ToolPackageVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tool_package_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_tool_package_versions_package_version"),
    )

    package_id = Column(String(36), ForeignKey("tool_packages.id"), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    manifest = Column(JSON, nullable=False)
    manifest_digest = Column(String(64), nullable=False, index=True)
    signature = Column(Text, nullable=True)
    is_signed = Column(Boolean, nullable=False, default=False, index=True)
    validation_status = Column(String(32), nullable=False, default="invalid", index=True)
    validation_errors = Column(JSON, nullable=False, default=list)

    package = relationship("ToolPackage", back_populates="versions", foreign_keys=[package_id])

