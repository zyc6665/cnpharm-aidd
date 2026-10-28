"""分片上传会话与数据集登记模型（docs/04 §5.8、§8）。

三张表解决两组问题：

* ``upload_sessions`` + ``upload_parts``：``>100MB`` 的文件必须走 Multipart 上传
  （docs/04 §13.2），而分片状态一旦存内存，多副本重启后用户就无法续传。因此会话
  落库，**已收到的分片单独成行**（``upload_parts``，``(session_id, part_number)``
  唯一），``object_key`` 保证「一个目标对象只有一个活会话」。
* ``datasets`` / ``data_files``：数据资产只登记「已完成的导入结果」——库内保存
  ``urn`` 与 ``sha256``，文件内容始终在 ``files`` 表 + 存储后端，避免第二份真值源
  （docs/04 §1）。

为什么分片不复用 ``upload_sessions.parts`` 这个 JSON 列
------------------------------------------------------
JSON 列只能整列读、整列写：两个并发 ``PUT /parts`` 都读到同一份旧数组、各自把
自己的片追加进去，后提交者会覆盖前者——**字节没丢（暂存里都在），索引却丢了**，
断点续传随即失效（PR #15 评审 B1 的复现路径）。改成一办法是给会话行加
``SELECT ... FOR UPDATE``，但 SQLite 根本没有行锁，测试环境与开发环境会得到与
生产不同的行为。因此把「一片一行」落到表里，用唯一约束 + 原生 upsert 让并发写入
互相覆盖同一条记录，而不是互相覆盖整列。

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

from app.common.time import utcnow
from app.database.base import Base, TimestampMixin, UUIDMixin

#: 分片上传会话状态机（docs/04 §5.8）。
UPLOAD_STATES = ("INITIATED", "UPLOADING", "COMPLETED", "ABORTED", "EXPIRED")

#: 数据集类型（docs/04 §8.1，docs/02 Q-03 的扩展形态见下）。
#:
#: 两类资产的处理方式不同：
#:
#: * **结构化资产** ``COMPOUND`` / ``PROTEIN`` / ``ACTIVITY``：文件会被解析成领域
#:   行（化合物、蛋白、活性记录），``row_count`` / ``summary`` 记录解析结果。
#: * **非结构资产** ``LITERATURE`` / ``EXPERIMENT`` / ``DOCUMENT``：**一律不解析**，
#:   只登记文件（``file_urn`` → ``data_files``）+ 结构化属性字段（落在
#:   ``Dataset.summary``）。这是 docs/02 Q-03 的结论——「文献」与「实验数据」的
#:   具体形态 = 以附件与结构化属性字段承载；若需文献检索/解析需另立需求。
#:
#: 三个非结构类型的差别只在「装什么」，处理方式相同（都不解析、只登记）：
#:
#: - ``LITERATURE``：文献（论文、专利、期刊附件等）；
#: - ``EXPERIMENT``：实验数据（仪器导出、实验记录、测定结果等）；
#: - ``DOCUMENT``：通用文档附件（方案、报告、SOP、规范等），G-13 新增。
DATASET_TYPES = (
    "COMPOUND",
    "PROTEIN",
    "ACTIVITY",
    "LITERATURE",
    "EXPERIMENT",
    "DOCUMENT",
)

#: 默认分片大小 16MB（docs/04 §5.8：2GB 上限 → ≤128 片）。
DEFAULT_PART_SIZE = 16 * 1024 * 1024


class UploadSession(Base, UUIDMixin, TimestampMixin):
    """分片上传会话（docs/04 §5.8）。

    已收到的分片在 ``upload_parts`` 子表里，不在本表上——原因见模块 docstring。
    """

    __tablename__ = "upload_sessions"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
        #: 幂等键唯一（docs/04 §5.5）。只有唯一约束才能挡住并发创建：先查后插在
        #: 两个请求同时到达时都会查到「不存在」，于是各建一个会话、返回两个不同
        #: uploadId，客户端后续的分片就分叉到两个会话里。
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_upload_sessions_project_idem"
        ),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    declared_filename = Column(String(255), nullable=False)
    declared_size = Column(BigInteger, nullable=False)
    #: 客户端预先算好的 sha256；给了就在合并时校验（docs/05 §4.2 的 42205 口径）。
    declared_sha256 = Column(String(64), nullable=True)
    content_type = Column(String(128), nullable=True)

    #: MinIO Multipart Upload ID；当前实现是「对象级分片暂存」，未使用原生
    #: Multipart Upload，因此保持 ``None``（见 ``app.files.part_staging``）。
    minio_upload_id = Column(String(255), nullable=True)
    object_key = Column(String(512), nullable=False)

    part_size = Column(Integer, nullable=False, default=DEFAULT_PART_SIZE)

    state = Column(String(16), nullable=False, default=UPLOAD_STATES[0], index=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    #: 幂等键（docs/04 §5.5 的 ``X-Idempotency-Key``）。单独成列而不是塞进
    #: 分片表：键需要在创建时就写入，而那时还没有任何分片。
    idempotency_key = Column(String(128), nullable=True)

    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])
    part_records = relationship(
        "UploadPart",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UploadPart.reported_at",
    )


class UploadPart(Base, TimestampMixin):
    """一个已收到的分片（``(session_id, part_number)`` 复合主键）。

    复合主键而不是 UUID 主键：业务上「一个会话里每个片号只有一条记录」，让数据库
    直接承担这个约束，写入方用 ``ON CONFLICT (session_id, part_number) DO UPDATE``
    重传同一片即可，不需要读-改-写。
    """

    __tablename__ = "upload_parts"

    session_id = Column(
        String(36),
        ForeignKey("upload_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    part_number = Column(Integer, primary_key=True)
    etag = Column(String(128), nullable=False)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    #: 首次收到该片的时间。列表按它排序，让 ``parts`` 保持「上报顺序」——
    #: 顺序本身没有语义（前端只用片号集合判断该重传哪些），但它让响应稳定可测。
    reported_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    session = relationship("UploadSession", back_populates="part_records")


class Dataset(Base, UUIDMixin, TimestampMixin):
    """数据集登记（docs/04 §8.1）。

    只存导入结果的引用（``file_urn``）与解析摘要（``summary``），**不复制文件内容**，
    也**不重新解析**——解析仍由既有的化合物导入用例完成。

    ``summary`` 这一 JSON 列同时承载**结构化属性字段**（docs/02 Q-03）：结构化资产
    存解析摘要（行数、列名、无效行统计等），``LITERATURE`` / ``EXPERIMENT`` /
    ``DOCUMENT`` 这类**不做解析**的非结构资产则把用户登记的结构化属性（如文献的
    DOI/作者/期刊、实验数据的仪器/批次/条件、文档的版本/生效日期）直接放在这里。
    结构化属性是「任意键值」的形态，JSON 列足够表达，因此不额外新增 ``attributes``
    列——加列只会让「解析摘要」与「结构化属性」分裂成两份真相源。
    """

    __tablename__ = "datasets"
    __table_args__ = (
        #: 同项目内同名同类型只允许一条：先查后插在并发下仍会落两条，登记接口
        #: 靠它把重复登记变成 409 而不是两条口径不同的记录。
        UniqueConstraint(
            "project_id", "name", "dataset_type", name="uq_datasets_project_name_type"
        ),
    )

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
    "UploadPart",
    "UploadSession",
]
