"""后台把卡位状态上报给平台（辅通道 C：POST /gpu/slots/report）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from .config import AgentSettings
from .core import AgentCore

logger = logging.getLogger(__name__)


class SlotReporter:
    def __init__(self, core: AgentCore, settings: AgentSettings) -> None:
        self.core = core
        self.settings = settings
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if not self.settings.platform_base_url or not self.settings.report_token:
            logger.warning(
                "未配置 DRP_PLATFORM_BASE_URL / DRP_AGENT_REPORT_TOKEN，跳过卡位状态上报"
            )
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        url = "%s/gpu/slots/report" % self.settings.platform_base_url
        headers = {"X-DRP-Agent-Token": self.settings.report_token or ""}
        async with httpx.AsyncClient(timeout=5.0) as client:
            while True:
                for item in self.core.slot_snapshot():
                    try:
                        await client.post(
                            url,
                            json={
                                "nodeId": item["nodeId"],
                                "slotId": item["slotId"],
                                "state": item["state"],
                                "message": item.get("message"),
                                "deviceCount": item.get("deviceCount"),
                            },
                            headers=headers,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("上报卡位失败 %s/%s: %s", item["nodeId"], item["slotId"], exc)
                await asyncio.sleep(self.settings.report_interval_seconds)
