"""python -m drp_node_agent 入口。"""
from __future__ import annotations

import logging

import uvicorn

from .config import load_settings
from .server import app


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
