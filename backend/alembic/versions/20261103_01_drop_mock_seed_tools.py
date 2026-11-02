"""Retire the demo mock tool rows seeded by ``20261029_01``.

Why this migration exists
=========================
``app/tools/capabilities.py`` no longer registers the demo-only mock model
packages, yet ``20261029_01_mock_model_packages`` still lists their six slugs in
``MOCK_PACKAGE_SLUGS``.  That seed migration bails out early when no owner (no
user) exists, so the standard "migrate first, create the first admin later"
deployment never writes the rows and the mismatch stays hidden.  The hazard is
real the moment someone runs the migrations from scratch against a database
that already has an admin: the six mock tools get inserted into ``tools`` while
the capability registry has no matching entry, producing a reverse
mismatch — the tool list advertises packages the canvas can no longer run.

This migration removes those stale rows.  It follows the retirement pattern of
``20261025_03_remove_external_database_tools``: a tool that a historical task
still references is kept for compatibility but flipped to
``status='disabled', is_public=false``; unreferenced tools are deleted, after
clearing their child rows.  ``tasks.tool_id`` is NOT NULL, so a referenced tool
can never be nulled out — it must be disabled.

``downgrade`` does not re-create anything: these are demo mock rows with no
data worth restoring, and the original seed revision still describes how to
recreate them.  It returns instead of raising so ``downgrade base`` keeps
working in the test suite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261103_01"
down_revision = "20261102_01"
branch_labels = None
depends_on = None


DROP_TOOL_SLUGS: tuple[str, ...] = (
    "admet-prediction",
    "std-diff-molecule-generation",
    "vina-virtual-screening",
    "gromacs-md-simulation",
    "gmx-mmpbsa-free-energy",
    "therapainter-peptide-design",
)

# Child tables that hold a foreign key onto ``tools.id``.
CHILD_TABLES: tuple[tuple[str, str], ...] = (
    ("tool_versions", "tool_id"),
    ("tool_capabilities", "tool_id"),
    ("tool_favorites", "tool_id"),
    ("tool_workbench_group_mappings", "tool_id"),
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _drop_tool_ids(bind: sa.engine.Connection) -> list[str]:
    rows = bind.execute(
        sa.text("SELECT id FROM tools WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": list(DROP_TOOL_SLUGS)},
    ).fetchall()
    return [str(row[0]) for row in rows]


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    if "tools" not in tables:
        return

    tool_ids = _drop_tool_ids(bind)
    if not tool_ids:
        return

    # Tasks keep a hard, NOT NULL FK onto ``tools.id`` for historical
    # traceability, so a tool that already ran stays as a disabled record
    # instead of being deleted (it cannot be nulled out).
    if "tasks" in tables:
        referenced = {
            str(row[0])
            for row in bind.execute(
                sa.text(
                    "SELECT DISTINCT tool_id FROM tasks WHERE tool_id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": tool_ids},
            ).fetchall()
        }
        if referenced:
            bind.execute(
                sa.text(
                    "UPDATE tools SET status = 'disabled', is_public = false "
                    "WHERE id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": list(referenced)},
            )
        tool_ids = [tool_id for tool_id in tool_ids if tool_id not in referenced]
        if not tool_ids:
            return

    for table_name, column_name in CHILD_TABLES:
        if table_name in tables:
            bind.execute(
                sa.text(
                    f"DELETE FROM {table_name} WHERE {column_name} IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": tool_ids},
            )

    # The association table has no surrogate key; clear it before the tool rows.
    if "tool_tag_map" in tables:
        bind.execute(
            sa.text("DELETE FROM tool_tag_map WHERE tool_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": tool_ids},
        )

    bind.execute(
        sa.text("DELETE FROM tools WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": tool_ids},
    )


def downgrade() -> None:
    """Nothing to restore: the demo rows are disposable and 20261029_01 owns them."""
    return
