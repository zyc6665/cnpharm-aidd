"""upload_sessions / datasets / data_files（docs/04 §5.8、§8）

三个能力一个迁移：

* ``upload_sessions``：>100MB 文件强制 Multipart（docs/04 §13.2）。会话状态一旦
  只存内存，多副本重启后用户无法续传，因此落库；``parts`` 用 JSON 存已完成分片。
* ``datasets`` / ``data_files``：数据资产只登记 urn + sha256，文件内容仍在
  ``files`` 表与存储后端（docs/04 §1），避免第二份真值源。

与 PR1 的 ``20261027_01`` 同一个 base（``20261026_04``），由 ``20261027_03``
merge 迁移收敛双 head。

Revision ID: 20261027_02
Revises: 20261026_04
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20261027_02"
down_revision = "20261026_04"
branch_labels = None
depends_on = None


UPLOAD_SESSIONS = "upload_sessions"
DATASETS = "datasets"
DATA_FILES = "data_files"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    table_names = _table_names()
    if UPLOAD_SESSIONS not in table_names:
        op.create_table(
            UPLOAD_SESSIONS,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("declared_filename", sa.String(length=255), nullable=False),
            sa.Column("declared_size", sa.BigInteger(), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=True),
            sa.Column("minio_upload_id", sa.String(length=255), nullable=True),
            sa.Column("object_key", sa.String(length=512), nullable=False),
            sa.Column("part_size", sa.Integer(), nullable=False, server_default="16777216"),
            sa.Column("parts", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(length=16), nullable=False, server_default="INITIATED"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("object_key", name="uq_upload_sessions_object_key"),
        )
        op.create_index(
            "ix_upload_sessions_project_id", UPLOAD_SESSIONS, ["project_id"]
        )
        op.create_index("ix_upload_sessions_created_by", UPLOAD_SESSIONS, ["created_by"])
        op.create_index("ix_upload_sessions_state", UPLOAD_SESSIONS, ["state"])
        op.create_index(
            "ix_upload_sessions_idempotency_key", UPLOAD_SESSIONS, ["idempotency_key"]
        )

    if DATASETS not in table_names:
        op.create_table(
            DATASETS,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("dataset_type", sa.String(length=32), nullable=False),
            sa.Column("file_urn", sa.String(length=512), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("import_task_id", sa.String(length=36), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_datasets_project_id", DATASETS, ["project_id"])
        op.create_index("ix_datasets_created_by", DATASETS, ["created_by"])
        op.create_index("ix_datasets_dataset_type", DATASETS, ["dataset_type"])

    if DATA_FILES not in table_names:
        op.create_table(
            DATA_FILES,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "dataset_id",
                sa.String(length=36),
                sa.ForeignKey("datasets.id"),
                nullable=False,
            ),
            sa.Column("urn", sa.String(length=512), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=32), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column(
                "storage_tier",
                sa.String(length=16),
                nullable=False,
                server_default="STANDARD",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_data_files_dataset_id", DATA_FILES, ["dataset_id"])


def downgrade() -> None:
    table_names = _table_names()
    if DATA_FILES in table_names:
        indexes = _existing_indexes(DATA_FILES)
        if "ix_data_files_dataset_id" in indexes:
            op.drop_index("ix_data_files_dataset_id", table_name=DATA_FILES)
        op.drop_table(DATA_FILES)

    if DATASETS in table_names:
        indexes = _existing_indexes(DATASETS)
        for name in (
            "ix_datasets_dataset_type",
            "ix_datasets_created_by",
            "ix_datasets_project_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name=DATASETS)
        op.drop_table(DATASETS)

    if UPLOAD_SESSIONS in table_names:
        indexes = _existing_indexes(UPLOAD_SESSIONS)
        for name in (
            "ix_upload_sessions_idempotency_key",
            "ix_upload_sessions_state",
            "ix_upload_sessions_created_by",
            "ix_upload_sessions_project_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name=UPLOAD_SESSIONS)
        op.drop_table(UPLOAD_SESSIONS)
