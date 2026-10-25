"""Remove the external database fetch/query built-in tools.

The China Pharmaceutical delivery line runs in a private, offline network and
the deployment red line forbids any outbound domain.  The five built-ins that
reached out to RCSB PDB, PubChem, ChEMBL and PDBbind are therefore gone from the
capability registry and from the built-in executor, so their persisted tool rows
must be retired too — otherwise the tool list advertises capabilities that can
only fail at execution time.

Seeded rows come from ``20260728_01`` (query-*) and ``20260820_01`` (fetch-*).
``downgrade`` does not re-seed: the seed rows carry no data worth restoring, and
the original seed revisions still describe how to recreate them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261025_03"
down_revision = "20261025_02"
branch_labels = None
depends_on = None


RETIRED_TOOL_SLUGS: tuple[str, ...] = (
    "builtin-fetch-pdb",
    "builtin-fetch-ligand",
    "builtin-query-chembl",
    "builtin-query-pubchem",
    "builtin-query-pdbbind",
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


def _retired_tool_ids(bind: sa.engine.Connection) -> list[str]:
    rows = bind.execute(
        sa.text("SELECT id FROM tools WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": list(RETIRED_TOOL_SLUGS)},
    ).fetchall()
    return [str(row[0]) for row in rows]


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    if "tools" not in tables:
        return

    tool_ids = _retired_tool_ids(bind)
    if not tool_ids:
        return

    # Tasks keep a hard FK onto ``tools.id`` for historical traceability, so a
    # tool that already ran stays as a disabled record instead of being deleted.
    if "tasks" in tables:
        referenced = {
            str(row[0])
            for row in bind.execute(
                sa.text("SELECT DISTINCT tool_id FROM tasks WHERE tool_id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
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
                sa.text(f"DELETE FROM {table_name} WHERE {column_name} IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": tool_ids},
            )

    # The association table has no surrogate key; clear it before the tool rows.
    if "tool_tag_map" in tables:
        bind.execute(
            sa.text(
                "DELETE FROM tool_tag_map WHERE tool_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": tool_ids},
        )

    bind.execute(
        sa.text("DELETE FROM tools WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": tool_ids},
    )


def downgrade() -> None:
    """Nothing to restore: the seed revisions own these rows."""
    return
