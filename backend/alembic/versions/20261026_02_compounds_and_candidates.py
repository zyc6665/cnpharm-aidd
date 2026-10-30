"""Add compound / candidate / candidate_set / candidate_set_item / molecule_fingerprint.

M1「研发项目与数据管理」与 M3「AI 分子与多肽设计」的数据底座
（docs/04 §5.7、§7.1~§7.3）。此前平台没有任何分子实体：化合物只作为上传文件
存在，候选物只出现在任务输出的 CSV 里，导致：

* M1-BR-1「以 InChIKey 去重」无处落地，同一分子每次导入都是一个新文件；
* M3-FR-08「候选物比较 ≤6 个并排」没有可引用的候选物 ID；
* 候选集无法作为项目资产被工作流复用（M6-BR-3）；
* 相似性检索缺指纹真值源（docs/04 §5.7 明确指纹只存 ``molecule_fingerprints``）。

五张表的顺序按外键依赖排列：``compounds`` → ``candidates`` →
``candidate_sets`` → ``candidate_set_items``，``molecule_fingerprints`` 依赖
``compounds``。本迁移只建表，不含种子数据。

两处 SQLite 与 PostgreSQL 的差异在此显式处理：

* ``candidates.attrs`` 的 GIN 索引只在 PostgreSQL 建（SQLite 无 GIN）；
* ``molecule_fingerprints`` 的二进制列用 ``sa.LargeBinary``，PostgreSQL 上是
  ``bytea``、SQLite 上是 ``BLOB``。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


def _json_column_type():
    """PG 用 ``jsonb``（GIN 需要 jsonb 的操作符类），SQLite 用 JSON。"""

    return sa.JSON().with_variant(JSONB, "postgresql")


revision = "20261026_02"
down_revision = "20261026_01"
branch_labels = None
depends_on = None


TABLE_NAMES = (
    "compounds",
    "candidates",
    "candidate_sets",
    "candidate_set_items",
    "molecule_fingerprints",
)


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    existing = _existing_tables()

    if "compounds" not in existing:
        op.create_table(
            "compounds",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
            sa.Column("name", sa.String(128)),
            sa.Column("inchikey", sa.String(27), nullable=False),
            sa.Column("canonical_smiles", sa.String(2048), nullable=False),
            sa.Column("mol_formula", sa.String(128)),
            sa.Column("mol_weight", sa.Numeric(10, 3)),
            sa.Column("props", sa.JSON(), nullable=False),
            sa.Column("structure_urn", sa.String(512)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("inchikey", name="uq_compounds_inchikey"),
        )
        op.create_index("ix_compounds_created_by", "compounds", ["created_by"])
        op.create_index("ix_compounds_inchikey", "compounds", ["inchikey"])

    if "candidates" not in existing:
        op.create_table(
            "candidates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
            sa.Column(
                "candidate_type", sa.String(32), nullable=False, server_default="SMALL_MOLECULE"
            ),
            sa.Column("compound_id", sa.String(36), sa.ForeignKey("compounds.id")),
            sa.Column("peptide_sequence", sa.Text()),
            sa.Column("name", sa.String(128)),
            sa.Column("code", sa.String(128)),
            sa.Column("source", sa.String(32), nullable=False, server_default="DESIGN"),
            sa.Column("design_score", sa.Numeric(10, 4)),
            sa.Column("task_id", sa.String(36)),
            sa.Column("attrs", _json_column_type(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "(candidate_type = 'SMALL_MOLECULE' AND compound_id IS NOT NULL)"
                " OR (candidate_type = 'PEPTIDE' AND peptide_sequence IS NOT NULL)",
                name="ck_candidates_payload_matches_type",
            ),
        )
        op.create_index("ix_candidates_project_id", "candidates", ["project_id"])
        op.create_index("ix_candidates_created_by", "candidates", ["created_by"])
        op.create_index("ix_candidates_task_id", "candidates", ["task_id"])
        op.create_index("ix_candidates_compound_id", "candidates", ["compound_id"])
        op.create_index(
            "ix_candidates_project_type_created",
            "candidates",
            ["project_id", "candidate_type", "created_at"],
        )
        if _is_postgresql():
            # docs/04 §7.2 要求 attrs 建 GIN 索引（按设计条件/属性筛选）。
            op.create_index(
                "ix_candidates_attrs_gin",
                "candidates",
                ["attrs"],
                postgresql_using="gin",
            )

    if "candidate_sets" not in existing:
        op.create_table(
            "candidate_sets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_task_id", sa.String(36)),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_candidate_sets_project_id", "candidate_sets", ["project_id"])
        op.create_index("ix_candidate_sets_created_by", "candidate_sets", ["created_by"])
        op.create_index("ix_candidate_sets_source_task_id", "candidate_sets", ["source_task_id"])

    if "candidate_set_items" not in existing:
        op.create_table(
            "candidate_set_items",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "set_id", sa.String(36), sa.ForeignKey("candidate_sets.id"), nullable=False
            ),
            sa.Column(
                "candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=False
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("snapshot_score", sa.Numeric(10, 4)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "set_id", "candidate_id", name="uq_candidate_set_items_set_candidate"
            ),
        )
        op.create_index(
            "ix_candidate_set_items_candidate_id", "candidate_set_items", ["candidate_id"]
        )
        op.create_index(
            "ix_candidate_set_items_set_ordinal", "candidate_set_items", ["set_id", "ordinal"]
        )

    if "molecule_fingerprints" not in existing:
        op.create_table(
            "molecule_fingerprints",
            sa.Column(
                "compound_id",
                sa.String(36),
                sa.ForeignKey("compounds.id"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("fp_ecfp4", sa.LargeBinary()),
            sa.Column("fp_maccs", sa.LargeBinary()),
            sa.Column("fp_ecfp4_bits", sa.Integer(), nullable=False, server_default="2048"),
            sa.Column("rdkit_version", sa.String(32)),
            sa.Column("computed_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    existing = _existing_tables()
    for table_name in reversed(TABLE_NAMES):
        if table_name in existing:
            op.drop_table(table_name)
