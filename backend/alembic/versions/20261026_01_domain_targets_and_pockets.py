"""Add target / protein / protein_structure / pocket / pocket_residue tables.

M2「AI 靶点结构分析」的主数据底座（docs/04 §6.1~§6.5）。此前平台只有任务与
Artifact 两张泛化表，靶点、口袋、候选物都只能作为任务参数里的字符串存在，
导致：

* 口袋无法被「选定」并在多次设计/对接任务之间复用（PRD M2-FR-06 要求持久化）；
* 结果详情页无法回答「这条结构属于哪个靶点、这个口袋贡献了哪些残基」；
* 追溯包缺 `bizRef.targetId / pocketId` 的实际落点。

本迁移只建表，不含种子数据。五张表的顺序按外键依赖排列。
"""

import sqlalchemy as sa
from alembic import op


revision = "20261026_01"
down_revision = "20261025_03"
branch_labels = None
depends_on = None


TABLE_NAMES = (
    "targets",
    "proteins",
    "protein_structures",
    "pockets",
    "pocket_residues",
)


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "targets" not in existing:
        op.create_table(
            "targets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("target_type", sa.String(32), nullable=False, server_default="PROTEIN"),
            sa.Column("uniprot_id", sa.String(32)),
            sa.Column("gene_name", sa.String(64)),
            sa.Column("description", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_targets_project_id", "targets", ["project_id"])
        op.create_index("ix_targets_created_by", "targets", ["created_by"])
        op.create_index("ix_targets_name", "targets", ["name"])
        op.create_index("ix_targets_uniprot_id", "targets", ["uniprot_id"])

    if "proteins" not in existing:
        op.create_table(
            "proteins",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("target_id", sa.String(36), sa.ForeignKey("targets.id"), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("sequence", sa.Text(), nullable=False),
            sa.Column("seq_length", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(16), nullable=False, server_default="MANUAL"),
            sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_proteins_target_id", "proteins", ["target_id"])

    if "protein_structures" not in existing:
        op.create_table(
            "protein_structures",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "protein_id",
                sa.String(36),
                sa.ForeignKey("proteins.id"),
                nullable=False,
            ),
            sa.Column(
                "source_type",
                sa.String(16),
                nullable=False,
                server_default="IMPORTED",
            ),
            sa.Column("structure_urn", sa.String(512)),
            sa.Column("prepared_urn", sa.String(512)),
            sa.Column("pdbqt_urn", sa.String(512)),
            sa.Column("sha256", sa.String(64)),
            sa.Column("plddt_mean", sa.Numeric(5, 2)),
            sa.Column("plddt_urn", sa.String(512)),
            sa.Column("model_name", sa.String(64)),
            sa.Column("model_version", sa.String(64)),
            sa.Column("tool_name", sa.String(64)),
            sa.Column("tool_version", sa.String(64)),
            sa.Column("task_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_protein_structures_protein_id", "protein_structures", ["protein_id"])
        op.create_index(
            "ix_protein_structures_source_type", "protein_structures", ["source_type"]
        )
        op.create_index("ix_protein_structures_sha256", "protein_structures", ["sha256"])
        op.create_index("ix_protein_structures_task_id", "protein_structures", ["task_id"])

    if "pockets" not in existing:
        op.create_table(
            "pockets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "structure_id",
                sa.String(36),
                sa.ForeignKey("protein_structures.id"),
                nullable=False,
            ),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("score", sa.Numeric(10, 4)),
            sa.Column("volume", sa.Numeric(12, 3)),
            sa.Column("center_x", sa.Numeric(10, 3)),
            sa.Column("center_y", sa.Numeric(10, 3)),
            sa.Column("center_z", sa.Numeric(10, 3)),
            sa.Column("box_size_x", sa.Numeric(10, 3)),
            sa.Column("box_size_y", sa.Numeric(10, 3)),
            sa.Column("box_size_z", sa.Numeric(10, 3)),
            sa.Column("residue_count", sa.Integer()),
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tool_name", sa.String(64)),
            sa.Column("tool_version", sa.String(64)),
            sa.Column("task_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("structure_id", "rank", name="uq_pockets_structure_rank"),
        )
        op.create_index("ix_pockets_structure_id", "pockets", ["structure_id"])
        op.create_index("ix_pockets_selected", "pockets", ["selected"])
        op.create_index("ix_pockets_task_id", "pockets", ["task_id"])
        # 同一结构下最多一个「已选定」口袋（docs/04 §5.6）。
        op.create_index(
            "uq_pockets_selected_structure",
            "pockets",
            ["structure_id"],
            unique=True,
            sqlite_where=sa.text("selected = 1"),
            postgresql_where=sa.text("selected = true"),
        )

    if "pocket_residues" not in existing:
        op.create_table(
            "pocket_residues",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("pocket_id", sa.String(36), sa.ForeignKey("pockets.id"), nullable=False),
            sa.Column("chain", sa.String(8), nullable=False),
            sa.Column("residue_seq", sa.Integer(), nullable=False),
            sa.Column("residue_name", sa.String(8), nullable=False),
            sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("contribution", sa.Numeric(10, 4)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "pocket_id",
                "chain",
                "residue_seq",
                "residue_name",
                name="uq_pocket_residues_pocket_chain_position",
            ),
        )
        op.create_index("ix_pocket_residues_pocket_id", "pocket_residues", ["pocket_id"])
        op.create_index(
            "ix_pocket_residues_pocket_id_is_key", "pocket_residues", ["pocket_id", "is_key"]
        )


def downgrade() -> None:
    existing = _existing_tables()
    for table_name in reversed(TABLE_NAMES):
        if table_name in existing:
            op.drop_table(table_name)
