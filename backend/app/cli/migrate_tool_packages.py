"""Migrate legacy tool versions into Tool Package v1 records."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.database.session import async_session_factory, engine
from app.tool_packages.migration import migrate_tool_packages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="仅生成迁移报告，不写入数据库"
    )
    mode.add_argument(
        "--apply", action="store_true", help="写入不可变 Tool Package 版本"
    )
    return parser


async def _run(*, dry_run: bool) -> dict:
    try:
        async with async_session_factory() as db:
            summary = await migrate_tool_packages(db, dry_run=dry_run)
            if dry_run:
                await db.rollback()
            else:
                await db.commit()
            return summary.to_dict()
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    summary = asyncio.run(_run(dry_run=args.dry_run))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
