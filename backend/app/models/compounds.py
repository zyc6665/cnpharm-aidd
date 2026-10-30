"""Compound / candidate / candidate set / molecule fingerprint models (docs/04 §7).

四个业务概念分开建表，是因为它们的真值与生命周期不同：

``compounds``
    全平台的小分子去重主表。同一分子在多个项目里被导入只留一行，靠
    ``inchikey`` 唯一约束保证；因此**没有 project_id** —— 化合物不是某个项目的
    私产，项目只是通过 ``candidates`` 引用它。
``candidates``
    项目内的候选物。小分子通过 ``compound_id`` 指向 ``compounds``，多肽直接存
    ``peptide_sequence``，所以两列都可空但必须二选一（见 ``__table_args__``
    的检查约束）。
``candidate_sets`` / ``candidate_set_items``
    候选集合与集合项。``candidate_set_items.snapshot_score`` 保存加入时的评分
    快照，避免结论随候选物后续变化而失真（docs/04 §9.5 决策记录的同一动机）。
``molecule_fingerprints``
    指纹缓存，主键即 ``compound_id``。指纹**只存在这一张表**——docs/04 §7.1 v1.2
    明确把 ``compound.fingerprint`` 列废弃，因为两处存放会产生两份真值源，且批量
    导入与指纹回填会争抢同一行锁。
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from app.common.time import utcnow
from app.database.base import Base, TimestampMixin, UUIDMixin

#: docs/04 §4.2 通用枚举。
CANDIDATE_TYPE_SMALL_MOLECULE = "SMALL_MOLECULE"
CANDIDATE_TYPE_PEPTIDE = "PEPTIDE"
CANDIDATE_TYPES = (CANDIDATE_TYPE_SMALL_MOLECULE, CANDIDATE_TYPE_PEPTIDE)

MOL_SOURCE_IMPORT = "IMPORT"
MOL_SOURCE_DESIGN = "DESIGN"
MOL_SOURCE_SCREENING = "SCREENING"
MOL_SOURCE_MANUAL = "MANUAL"
MOL_SOURCES = (MOL_SOURCE_IMPORT, MOL_SOURCE_DESIGN, MOL_SOURCE_SCREENING, MOL_SOURCE_MANUAL)


class Compound(Base, UUIDMixin, TimestampMixin):
    """小分子去重主表（docs/04 §7.1）。

    ``inchikey`` 唯一：以 InChIKey 作为去重键而不是 SMILES，是因为同一分子的
    SMILES 写法（芳香性、互变异构、质子化态）可以有多种，InChIKey 是标准化后的
    结构标识（PRD M1-BR-1 明确要求「以 InChIKey 去重」）。

    ``props`` 存 RDKit 计算的性质（logP/TPSA/HBD/HBA/RotB/QED 等）。它是派生数据
    而非真值，允许重算覆盖；真值始终是 ``canonical_smiles``。
    """

    __tablename__ = "compounds"

    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(128), nullable=True)
    inchikey = Column(String(27), nullable=False, unique=True)
    canonical_smiles = Column(String(2048), nullable=False)
    mol_formula = Column(String(128), nullable=True)
    mol_weight = Column(Numeric(10, 3), nullable=True)
    props = Column(JSON, nullable=False, default=dict)
    #: 2D 渲染 SVG 或 MOL 文件的 URN（``file:{id}``），一期由前端 smiles-drawer 渲染，
    #: 该列预留给「保存标准 2D 结构图」的后续需求。
    structure_urn = Column(String(512), nullable=True)


class Candidate(Base, UUIDMixin, TimestampMixin):
    """项目内候选物（docs/04 §7.2）。

    小分子与多肽共表：``candidate_type`` 区分，``compound_id`` 与
    ``peptide_sequence`` 各有检查约束保证「该填的填了」。共表而不是两表，是因为
    候选集要能混装两类（M3-FR-08 候选物比较 ≤6 个并排，不区分类型）。
    """

    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint(
            "(candidate_type = 'SMALL_MOLECULE' AND compound_id IS NOT NULL)"
            " OR (candidate_type = 'PEPTIDE' AND peptide_sequence IS NOT NULL)",
            name="ck_candidates_payload_matches_type",
        ),
        Index("ix_candidates_project_type_created", "project_id", "candidate_type", "created_at"),
        Index("ix_candidates_project_created", "project_id", "created_at"),
        Index("ix_candidates_compound_id", "compound_id"),
        # JSON attrs 的包含查询（docs/04 §7.2）：PG-only GIN，与迁移 20261026_02:110
        # 的建法一致；SQLite 无 GIN，create_all 时会忽略 postgresql_using 变成普通索引。
        Index("ix_candidates_attrs_gin", "attrs", postgresql_using="gin"),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    candidate_type = Column(String(32), nullable=False, default=CANDIDATE_TYPE_SMALL_MOLECULE)
    compound_id = Column(String(36), ForeignKey("compounds.id"), nullable=True)
    peptide_sequence = Column(Text, nullable=True)
    name = Column(String(128), nullable=True)
    code = Column(String(128), nullable=True)
    source = Column(String(32), nullable=False, default=MOL_SOURCE_DESIGN)
    design_score = Column(Numeric(10, 4), nullable=True)
    #: 产出该候选物的任务；与 ``protein_structures.task_id`` 同样只存字符串不建外键，
    #: 任务有独立归档与清理策略（docs/04 §9.1）。
    task_id = Column(String(36), nullable=True, index=True)
    #: 设计条件、修饰、自定义属性（docs/04 §7.2 要求 GIN 索引，PostgreSQL 侧由迁移
    #: 单独创建；SQLite 无 GIN，迁移里跳过）。
    attrs = Column(JSON, nullable=False, default=dict)


class CandidateSet(Base, UUIDMixin, TimestampMixin):
    """候选集合（docs/04 §7.3）。

    ``item_count`` 是冗余计数，用于列表页避免每次 ``COUNT(*)``；写入集合项时在同
    一事务内维护，不做触发器（触发器在 SQLite 与 PostgreSQL 行为差异更大）。
    """

    __tablename__ = "candidate_sets"
    __table_args__ = (
        # 项目内候选集列表：project_id 过滤、按 created_at 倒序翻页。
        Index("ix_candidate_sets_project_created", "project_id", "created_at"),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    item_count = Column(Integer, nullable=False, default=0)
    source_task_id = Column(String(36), nullable=True, index=True)
    #: 乐观锁版本号：docs/04 §5.6 把 ``candidate_set`` 列入「启用乐观锁的可编辑业务
    #: 表」，写入时 ``UPDATE ... WHERE id=? AND version=?``，影响行数 0 → 40903。
    version = Column(Integer, nullable=False, default=1)
    is_archived = Column(Boolean, nullable=False, default=False)


class CandidateSetItem(Base, UUIDMixin, TimestampMixin):
    """集合项（docs/04 §7.3）。唯一约束 ``(set_id, candidate_id)`` 防重复加入。"""

    __tablename__ = "candidate_set_items"
    __table_args__ = (
        UniqueConstraint("set_id", "candidate_id", name="uq_candidate_set_items_set_candidate"),
        Index("ix_candidate_set_items_set_ordinal", "set_id", "ordinal"),
    )

    set_id = Column(String(36), ForeignKey("candidate_sets.id"), nullable=False)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False, default=0)
    #: 加入时的评分快照，之后候选物评分变化不影响历史集合（与决策记录快照同一动机）。
    snapshot_score = Column(Numeric(10, 4), nullable=True)


class MoleculeFingerprint(Base):
    """分子指纹缓存（docs/04 §5.7）。

    主键即 ``compound_id``：一个化合物只有一份指纹，不需要额外 id。指纹列用
    ``LargeBinary``（PostgreSQL 上是 ``bytea``，SQLite 上是 BLOB）。

    **性能口径**（docs/04 §5.7）：一期相似性检索是全表扫描 + 应用内 Tanimoto，
    不建任何指纹列索引；限制项目内候选数 ≤ 20000（``SERVICE_MAX_PROJECT_CANDIDATES``）。
    """

    __tablename__ = "molecule_fingerprints"

    compound_id = Column(
        String(36), ForeignKey("compounds.id"), primary_key=True, nullable=False
    )
    #: ECFP4，2048 bit = 256 字节。
    fp_ecfp4 = Column(LargeBinary, nullable=True)
    #: MACCS 167 bit。
    fp_maccs = Column(LargeBinary, nullable=True)
    fp_ecfp4_bits = Column(Integer, nullable=False, default=2048)
    #: 生成指纹的 RDKit 版本，纳入追溯——不同版本的指纹不可比。
    rdkit_version = Column(String(32), nullable=True)
    computed_at = Column(DateTime, nullable=False, default=utcnow)
