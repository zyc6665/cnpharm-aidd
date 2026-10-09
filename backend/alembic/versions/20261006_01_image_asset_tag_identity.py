"""Allow multiple tags to reference the same image manifest."""

import sqlalchemy as sa
from alembic import op


revision = "20261006_01"
down_revision = "20261004_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "image_assets" not in set(sa.inspect(bind).get_table_names()):
        return

    unique_constraints = sa.inspect(bind).get_unique_constraints("image_assets")
    has_tag_identity = any(
        set(constraint.get("column_names") or []) == {"repository", "tag"}
        for constraint in unique_constraints
    )
    digest_constraint = next(
        (
            constraint
            for constraint in unique_constraints
            if set(constraint.get("column_names") or [])
            == {"repository", "manifest_digest"}
        ),
        None,
    )
    if has_tag_identity:
        return

    with op.batch_alter_table("image_assets", recreate="always") as batch:
        if digest_constraint and digest_constraint.get("name"):
            batch.drop_constraint(digest_constraint["name"], type_="unique")
        batch.create_unique_constraint(
            "uq_image_assets_repository_tag",
            ["repository", "tag"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "image_assets" not in set(sa.inspect(bind).get_table_names()):
        return

    unique_constraints = sa.inspect(bind).get_unique_constraints("image_assets")
    has_digest_identity = any(
        set(constraint.get("column_names") or []) == {"repository", "manifest_digest"}
        for constraint in unique_constraints
    )
    tag_constraint = next(
        (
            constraint
            for constraint in unique_constraints
            if set(constraint.get("column_names") or []) == {"repository", "tag"}
        ),
        None,
    )
    if has_digest_identity:
        return

    with op.batch_alter_table("image_assets", recreate="always") as batch:
        if tag_constraint and tag_constraint.get("name"):
            batch.drop_constraint(tag_constraint["name"], type_="unique")
        batch.create_unique_constraint(
            "uq_image_assets_repository_digest",
            ["repository", "manifest_digest"],
        )
