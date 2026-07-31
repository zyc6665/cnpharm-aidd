"""Backfill legacy resources into default research projects."""

from __future__ import annotations

import argparse
import asyncio

from app.database.session import async_session_factory, engine
from app.services.project_migration import backfill_legacy_projects


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="仅统计，不写入数据库")
    mode.add_argument("--apply", action="store_true", help="执行幂等回填")
    return parser


async def _run(*, dry_run: bool) -> None:
    try:
        async with async_session_factory() as db:
            result = await backfill_legacy_projects(db, dry_run=dry_run)
            if dry_run:
                await db.rollback()
            else:
                await db.commit()
    finally:
        await engine.dispose()
    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(
        f"{mode}: users={result.users_processed} "
        f"projects={result.projects_created} resources={result.resources_linked} "
        f"unowned={result.unowned_resources}",
        flush=True,
    )


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
