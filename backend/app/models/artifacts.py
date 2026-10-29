"""Typed, versioned research Artifact persistence models."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class Artifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "artifacts"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    artifact_type = Column(String(100), nullable=False, index=True)
    semantic_type = Column(String(100), nullable=False, index=True)
    standard_type = Column(String(100), nullable=True, index=True)
    standard_version = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    latest_version_id = Column(String(36), nullable=True)
    source_task_id = Column(String(36), nullable=True, index=True)

    versions = relationship(
        "ArtifactVersion",
        back_populates="artifact",
        cascade="all, delete-orphan",
        foreign_keys="ArtifactVersion.artifact_id",
        order_by="ArtifactVersion.version",
    )
    latest_version = relationship(
        "ArtifactVersion",
        foreign_keys=[latest_version_id],
        primaryjoin="Artifact.latest_version_id==ArtifactVersion.id",
        uselist=False,
        post_update=True,
    )


class ArtifactVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
        Index(
            "uq_artifact_versions_artifact_sha256",
            "artifact_id",
            "sha256",
            unique=True,
            sqlite_where=text("status = 'available'"),
            postgresql_where=text("status = 'available'"),
        ),
    )

    artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(160), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_key = Column(String(1000), nullable=False)
    storage_etag = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="available", index=True)
    validation_status = Column(String(32), nullable=False, default="pending", index=True)
    validation_errors = Column(JSON, nullable=False, default=list)
    manifest_json = Column(JSON, nullable=False, default=dict)
    summary_json = Column(JSON, nullable=False, default=dict)
    metrics_json = Column(JSON, nullable=False, default=dict)
    expires_at = Column(DateTime, nullable=True, index=True)
    source_task_id = Column(String(36), nullable=True, index=True)
    source_attempt_id = Column(String(64), nullable=True)
    source_tool_version_id = Column(String(36), nullable=True)
    storage_tier = Column(
        String(16), nullable=False, default="standard", server_default="standard"
    )

    artifact = relationship("Artifact", back_populates="versions", foreign_keys=[artifact_id])
    files = relationship(
        "ArtifactVersionFile",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="ArtifactVersionFile.sort_order",
    )


class ArtifactVersionFile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "artifact_version_files"
    __table_args__ = (
        UniqueConstraint(
            "artifact_version_id",
            "role",
            name="uq_artifact_version_files_version_role",
        ),
    )

    artifact_version_id = Column(
        String(36), ForeignKey("artifact_versions.id"), nullable=False, index=True
    )
    role = Column(String(100), nullable=False, index=True)
    file_id = Column(String(36), ForeignKey("files.id"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)

    version = relationship("ArtifactVersion", back_populates="files")
    file = relationship("File")


class ArtifactLineage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "artifact_lineage"
    __table_args__ = (
        UniqueConstraint(
            "input_version_id",
            "output_version_id",
            name="uq_artifact_lineage_input_output",
        ),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    input_version_id = Column(
        String(36), ForeignKey("artifact_versions.id"), nullable=False, index=True
    )
    output_version_id = Column(
        String(36), ForeignKey("artifact_versions.id"), nullable=False, index=True
    )
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    relation_type = Column(String(32), nullable=False, default="derived_from")
