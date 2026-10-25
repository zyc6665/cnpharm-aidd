"""分片上传会话与数据集登记模型（docs/04 §5.8、§8）。

三张表解决两组问题：

* ``upload_sessions``：``>100MB`` 的文件必须走 Multipart 上传（docs/04 §13.2），
  而分片状态一旦存内存，多副本重启后用户就无法续传。因此会话与已完成分片
  落库（``parts`` JSON 列），``object_key`` 保证「一个目标对象只有一个活会话」。
* ``datasets`` / ``data_files``：数据资产只登记「已完成的导入结果」——库内保存
  ``urn`` 与 ``sha256``，文件内容始终在 ``files`` 表 + 存储后端，避免第二份真值源
  （docs/04 §1）。

字段口径严格对齐 docs/04 §5.8 与 §8；本模块只声明结构，业务用例在
``app.services.uploads`` / ``app.services.datasets``。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

#: 分片上传会话状态机（docs/04 §5.8）。
UPLOAD_STATES = ("INITIATED", "UPLOADING", "COMPLETED", "ABORTED", "EXPIRED")

#: 数据集类型（docs/04 §8.1）。
DATASET_TYPES = ("COMPOUND", "PROTEIN", "ACTIVITY", "LITERATURE", "EXPERIMENT")

#: 默认分片大小 16MB（docs/04 §5.8：2GB 上限 → ≤128 片）。
DEFAULT_PART_SIZE = 16 * 1024 * 1024


class UploadSession(Base, UUIDMixin, TimestampMixin):
    """分片上传会话（docs/04 §5.8）。

    ``parts`` 是已完成分片的有序列表 ``[{partNumber, etag, size}]``。它是 JSON 列，
    **原地 append 不会被 SQLAlchemy 感知**，写入方必须整列重新赋值（见
    ``app.services.uploads.record_upload_part``）。
    """

    __tablename__ = "upload_sessions"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    declared_filename = Column(String(255), nullable=False)
    declared_size = Column(BigInteger, nullable=False)
    content_type = Column(String(128), nullable=True)

    #: MinIO Multipart Upload ID；本地落盘实现下为 ``None``，接入 MinIO 直传后回填。
    minio_upload_id = Column(String(255), nullable=True)
    object_key = Column(String(512), nullable=False)

    part_size = Column(Integer, nullable=False, default=DEFAULT_PART_SIZE)
    parts = Column(JSON, nullable=False, default=list)

    state = Column(String(16), nullable=False, default=UPLOAD_STATES[0], index=True)
    expires_at = Column(DateTime, nullable=True)

    #: 幂等键（docs/04 §5.5 的 ``X-Idempotency-Key``）。单独成列而不是塞进 ``parts``
    #: 或 ``summary``：键需要在创建时就写入，而那时还没有任何分片。
    idempotency_key = Column(String(128), nullable=True, index=True)

    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])


class Dataset(Base, UUIDMixin, TimestampMixin):
    """数据集登记（docs/04 §8.1）。

    只存导入结果的引用（``file_urn``）与解析摘要（``summary``），**不复制文件内容**，
    也**不重新解析**——解析仍由既有的化合物导入用例完成。
    """

    __tablename__ = "datasets"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(128), nullable=False)
    dataset_type = Column(String(32), nullable=False, index=True)
    file_urn = Column(String(512), nullable=False)
    row_count = Column(Integer, nullable=False, default=0)
    import_task_id = Column(String(36), nullable=True)
    summary = Column(JSON, nullable=False, default=dict)

    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])
    files = relationship(
        "DataFile",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DataFile(Base, UUIDMixin, TimestampMixin):
    """数据集包含的物理文件（docs/04 §8.2）。

    一个数据集可以由多个文件组成（例如一次导入拆成多个 SDF 批次），因此与
    ``datasets`` 是 1:N 而非内嵌数组；``storage_tier`` 用于后续冷热分层。
    """

    __tablename__ = "data_files"

    dataset_id = Column(
        String(36), ForeignKey("datasets.id"), nullable=False, index=True
    )
    urn = Column(String(512), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    storage_tier = Column(String(16), nullable=False, default="STANDARD")

    dataset = relationship("Dataset", back_populates="files")


__all__ = [
    "DATASET_TYPES",
    "DEFAULT_PART_SIZE",
    "DataFile",
    "Dataset",
    "UPLOAD_STATES",
    "UploadSession",
]
