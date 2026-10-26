"""Data version ledger: the history of an entity, next to its current state.

``data_versions`` (docs/04 §8.3) answers "这个实体被改过几次、每次改成了什么",
which the entity tables themselves cannot answer: ``compounds.canonical_smiles``,
``proteins.sequence`` / ``proteins.current_version`` and ``datasets.file_urn``
each hold **当前态** — one row per entity, overwritten in place. Reading a
month-old 追溯包 therefore needs a second, per-version record rather than a
wider column on the entity row.

The ledger is **只追加** (docs/10 DB-09): a version row is written once, when the
entity is created or recomputed, and is never updated or deleted. History that
can be rewritten is not history — if an operator could edit row 3, the diff
between row 3 and row 4 would stop describing what the pipeline actually
produced. Corrections are expressed as a *new* version, keeping every prior row
intact.

``version`` starts at 1 for every entity and increases monotonically. The pair
``(entity_type, entity_id, version)`` is unique, so two concurrent writers
cannot both claim version N — the loser of that race retries with N+1 (see
``app.services.data_versions.record_version``).
"""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, Text, UniqueConstraint

from app.database.base import Base, TimestampMixin, UUIDMixin

#: docs/04 §8.3 实体类型枚举。
ENTITY_TYPE_COMPOUND = "COMPOUND"
ENTITY_TYPE_PROTEIN = "PROTEIN"
ENTITY_TYPE_DATASET = "DATASET"
ENTITY_TYPES = (ENTITY_TYPE_COMPOUND, ENTITY_TYPE_PROTEIN, ENTITY_TYPE_DATASET)

#: docs/04 §8.3 版本来源枚举。
SOURCE_TYPE_IMPORT = "IMPORT"
SOURCE_TYPE_COMPUTE = "COMPUTE"
SOURCE_TYPE_MANUAL = "MANUAL"
SOURCE_TYPES = (SOURCE_TYPE_IMPORT, SOURCE_TYPE_COMPUTE, SOURCE_TYPE_MANUAL)


class DataVersion(Base, UUIDMixin, TimestampMixin):
    """数据版本（只追加）— docs/04 §8.3.

    ``operator`` stores the operator's username snapshot rather than a foreign
    key: the version history must stay readable after a user is renamed or
    disabled (docs/04 §3 note 1, the same reasoning as ``AuditLog.actor``).
    There is deliberately no ``operator_id`` here — unlike the audit trail this
    table is read as "谁在什么时候把实体改成了这样", and a join to ``users``
    would make the answer change whenever the account is edited.

    ``content_hash`` is the sha256 hex of the versioned content (see
    ``app.services.data_versions.content_hash_of``), so "两次导入的内容是否真的
    不同" can be answered without diffing the payloads. ``source_file_urn`` and
    ``change_summary`` are nullable because not every version comes from a file
    (``COMPUTE``) or carries a human note.
    """

    __tablename__ = "data_versions"
    # 索引只在 ``__table_args__`` 声明（与 ``models/idempotency.py`` 同一约定）：
    # 列上再写 ``index=True`` 会让 ``Base.metadata.create_all``（开发/测试）与
    # Alembic（生产）产生同名索引的两种来源，漂移只在生产暴露。
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "version",
            name="uq_data_versions_entity_version",
        ),
        # 列表查询固定按 (entity_type, entity_id) 过滤、按 created_at 倒序翻页，
        # 故把 created_at 放进同一个索引，避免回表排序。
        Index("ix_data_versions_entity", "entity_type", "entity_id", "created_at"),
    )

    entity_type = Column(String(32), nullable=False)
    entity_id = Column(String(36), nullable=False)
    version = Column(Integer, nullable=False)
    source_type = Column(String(32), nullable=False)
    source_file_urn = Column(String(512), nullable=True)
    change_summary = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    operator = Column(String(64), nullable=True)


__all__ = [
    "DataVersion",
    "ENTITY_TYPES",
    "ENTITY_TYPE_COMPOUND",
    "ENTITY_TYPE_DATASET",
    "ENTITY_TYPE_PROTEIN",
    "SOURCE_TYPES",
    "SOURCE_TYPE_COMPUTE",
    "SOURCE_TYPE_IMPORT",
    "SOURCE_TYPE_MANUAL",
]
