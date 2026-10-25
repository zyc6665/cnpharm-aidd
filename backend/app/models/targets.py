"""Target, protein, structure, pocket domain models (docs/04 §6).

本模块承载 M2「AI 靶点结构分析」的领域主数据：

    target ──< protein ──< protein_structure ──< pocket ──< pocket_residue

设计口径（与 docs/04 §6 一致）：
- 主键沿用平台既有约定 `String(36)` UUID（`UUIDMixin`），不引入前缀化 ULID，
  避免同一个库出现两套主键形态。
- `task_id` 只存字符串不建外键：任务表有独立的归档策略，删除任务不应连带
  删除领域数据（追溯链靠 `task_input_snapshot` 与 Artifact lineage 维持）。
- `pocket.selected` 建**分区唯一索引**：同一结构下最多一个口袋被选定。
"""

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


TARGET_TYPE_PROTEIN = "PROTEIN"

PROTEIN_SOURCE_IMPORT = "IMPORT"
PROTEIN_SOURCE_MANUAL = "MANUAL"

STRUCTURE_SOURCE_PREDICTED = "PREDICTED"
STRUCTURE_SOURCE_IMPORTED = "IMPORTED"
STRUCTURE_SOURCE_PREPARED = "PREPARED"

PROTEIN_SOURCES = (PROTEIN_SOURCE_IMPORT, PROTEIN_SOURCE_MANUAL)
STRUCTURE_SOURCE_TYPES = (
    STRUCTURE_SOURCE_PREDICTED,
    STRUCTURE_SOURCE_IMPORTED,
    STRUCTURE_SOURCE_PREPARED,
)


class Target(Base, UUIDMixin, TimestampMixin):
    """靶点（docs/04 §6.1）。"""

    __tablename__ = "targets"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, default=TARGET_TYPE_PROTEIN)
    uniprot_id = Column(String(32), nullable=True, index=True)
    gene_name = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)

    proteins = relationship(
        "Protein",
        back_populates="target",
        cascade="all, delete-orphan",
        order_by="Protein.created_at",
    )


class Protein(Base, UUIDMixin, TimestampMixin):
    """蛋白质序列母记录（docs/04 §6.2）。"""

    __tablename__ = "proteins"

    target_id = Column(String(36), ForeignKey("targets.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    sequence = Column(Text, nullable=False)
    seq_length = Column(Integer, nullable=False)
    source = Column(String(16), nullable=False, default=PROTEIN_SOURCE_MANUAL)
    current_version = Column(Integer, nullable=False, default=1)

    target = relationship("Target", back_populates="proteins")
    structures = relationship(
        "ProteinStructure",
        back_populates="protein",
        cascade="all, delete-orphan",
        order_by="ProteinStructure.created_at",
    )


class ProteinStructure(Base, UUIDMixin, TimestampMixin):
    """蛋白结构（docs/04 §6.3）。预测、导入、准备三类结构共用一张表。"""

    __tablename__ = "protein_structures"

    protein_id = Column(String(36), ForeignKey("proteins.id"), nullable=False, index=True)
    source_type = Column(String(16), nullable=False, default=STRUCTURE_SOURCE_IMPORTED, index=True)
    structure_urn = Column(String(512), nullable=True)
    prepared_urn = Column(String(512), nullable=True)
    pdbqt_urn = Column(String(512), nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    plddt_mean = Column(Numeric(5, 2), nullable=True)
    plddt_urn = Column(String(512), nullable=True)
    model_name = Column(String(64), nullable=True)
    model_version = Column(String(64), nullable=True)
    tool_name = Column(String(64), nullable=True)
    tool_version = Column(String(64), nullable=True)
    task_id = Column(String(36), nullable=True, index=True)

    protein = relationship("Protein", back_populates="structures")
    pockets = relationship(
        "Pocket",
        back_populates="structure",
        cascade="all, delete-orphan",
        order_by="Pocket.rank",
    )


class Pocket(Base, UUIDMixin, TimestampMixin):
    """结合口袋（docs/04 §6.4）。"""

    __tablename__ = "pockets"
    __table_args__ = (
        UniqueConstraint("structure_id", "rank", name="uq_pockets_structure_rank"),
        # docs/04 §5.6：同一结构下只允许一个口袋被选定为下游设计/对接约束。
        Index(
            "uq_pockets_selected_structure",
            "structure_id",
            unique=True,
            sqlite_where=text("selected = 1"),
            postgresql_where=text("selected = true"),
        ),
    )

    structure_id = Column(
        String(36), ForeignKey("protein_structures.id"), nullable=False, index=True
    )
    rank = Column(Integer, nullable=False)
    score = Column(Numeric(10, 4), nullable=True)
    volume = Column(Numeric(12, 3), nullable=True)
    center_x = Column(Numeric(10, 3), nullable=True)
    center_y = Column(Numeric(10, 3), nullable=True)
    center_z = Column(Numeric(10, 3), nullable=True)
    box_size_x = Column(Numeric(10, 3), nullable=True)
    box_size_y = Column(Numeric(10, 3), nullable=True)
    box_size_z = Column(Numeric(10, 3), nullable=True)
    residue_count = Column(Integer, nullable=True)
    selected = Column(Boolean, nullable=False, default=False, index=True)
    tool_name = Column(String(64), nullable=True)
    tool_version = Column(String(64), nullable=True)
    task_id = Column(String(36), nullable=True, index=True)

    structure = relationship("ProteinStructure", back_populates="pockets")
    residues = relationship(
        "PocketResidue",
        back_populates="pocket",
        cascade="all, delete-orphan",
        order_by="PocketResidue.residue_seq",
    )


class PocketResidue(Base, UUIDMixin, TimestampMixin):
    """口袋残基（docs/04 §6.5）。"""

    __tablename__ = "pocket_residues"
    __table_args__ = (
        UniqueConstraint(
            "pocket_id",
            "chain",
            "residue_seq",
            "residue_name",
            name="uq_pocket_residues_pocket_chain_position",
        ),
        Index("ix_pocket_residues_pocket_id_is_key", "pocket_id", "is_key"),
    )

    pocket_id = Column(String(36), ForeignKey("pockets.id"), nullable=False, index=True)
    chain = Column(String(8), nullable=False)
    residue_seq = Column(Integer, nullable=False)
    residue_name = Column(String(8), nullable=False)
    is_key = Column(Boolean, nullable=False, default=False)
    contribution = Column(Numeric(10, 4), nullable=True)

    pocket = relationship("Pocket", back_populates="residues")
