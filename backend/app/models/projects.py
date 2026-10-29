"""Organization and research project models."""

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"

    name = Column(String(160), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)

    projects = relationship("Project", back_populates="organization")


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False, index=True)
    goal = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    model_policy = Column(JSON, nullable=False, default=dict)
    data_policy = Column(JSON, nullable=False, default=dict)
    # 乐观锁版本号：每次更新 +1，客户端用 expected_version 做条件更新。
    version = Column(Integer, nullable=False, default=1, server_default="1")

    organization = relationship("Organization", back_populates="projects")
    creator = relationship("User")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),)

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False, index=True)

    project = relationship("Project", back_populates="members")
    user = relationship("User")
