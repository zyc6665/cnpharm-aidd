"""HTTP discovery client for remote-tool.v1 services."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.remote_tools.diagnostics import RemoteToolStageDiagnostic
from app.remote_tools.schemas import RemoteToolExamplesResponse, RemoteToolManifest


DISCOVERY_MANIFEST_PATH = "/.well-known/sciminer-tool.json"


class RemoteToolDiscoveryResult(BaseModel):
    """Collected discovery documents plus stage diagnostics."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: RemoteToolManifest | None = None
    health: dict[str, Any] | None = None
    examples: RemoteToolExamplesResponse | None = None
    stages: list[RemoteToolStageDiagnostic] = Field(default_factory=list)


class RemoteToolDiscoveryClient:
    """Fetch and validate the fixed remote-tool.v1 discovery documents."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport
        self.request_id = str(uuid.uuid4())

    async def discover(self) -> RemoteToolDiscoveryResult:
        stages: list[RemoteToolStageDiagnostic] = []

        manifest_payload, fetch_stage = await self._fetch_json(DISCOVERY_MANIFEST_PATH)
        stages.append(fetch_stage)
        if fetch_stage.status != "success":
            return RemoteToolDiscoveryResult(stages=stages)

        try:
            manifest = RemoteToolManifest.model_validate(manifest_payload)
        except ValidationError as exc:
            stages.append(
                RemoteToolStageDiagnostic(
                    name="validate_manifest",
                    status="failure",
                    message=str(exc),
                )
            )
            return RemoteToolDiscoveryResult(stages=stages)

        stages.append(
            RemoteToolStageDiagnostic(
                name="validate_manifest",
                status="success",
                message="Manifest is valid",
            )
        )

        health_payload, health_stage = await self._fetch_json(
            manifest.endpoints.health,
            stage_name="health_check",
        )
        stages.append(health_stage)
        health = health_payload if isinstance(health_payload, dict) else None

        examples_payload, examples_stage = await self._fetch_json(
            manifest.endpoints.examples,
            stage_name="fetch_examples",
        )
        examples: RemoteToolExamplesResponse | None = None
        if examples_stage.status == "success":
            try:
                examples = RemoteToolExamplesResponse.model_validate(examples_payload)
            except ValidationError as exc:
                examples_stage = RemoteToolStageDiagnostic(
                    name="fetch_examples",
                    status="failure",
                    message=str(exc),
                )
        stages.append(examples_stage)

        return RemoteToolDiscoveryResult(
            manifest=manifest,
            health=health,
            examples=examples,
            stages=stages,
        )

    async def _fetch_json(
        self,
        path: str,
        *,
        stage_name: str = "fetch_manifest",
    ) -> tuple[Any | None, RemoteToolStageDiagnostic]:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    self._url(path),
                    headers={"X-Sciminer-Request-Id": self.request_id},
                )
            response.raise_for_status()
            return response.json(), RemoteToolStageDiagnostic(
                name=stage_name,
                status="success",
                message="Loaded",
            )
        except httpx.HTTPStatusError as exc:
            return None, RemoteToolStageDiagnostic(
                name=stage_name,
                status="failure",
                message=f"HTTP {exc.response.status_code} while loading {path}",
            )
        except Exception as exc:
            return None, RemoteToolStageDiagnostic(
                name=stage_name,
                status="failure",
                message=f"Failed to load {path}: {exc}",
            )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

