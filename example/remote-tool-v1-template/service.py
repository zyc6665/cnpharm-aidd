"""Minimal Remote Tool v1 reference service.

Run locally with:
    uvicorn service:create_app --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response


PROTEIN_EXAMPLE_BYTES = b"ATOM      1  N   GLY A   1       0.000   0.000   0.000\nEND\n"
RESIDUE_POCKET_BYTES = b"ATOM      1  CA  GLY A   1       1.000   1.000   1.000\nEND\n"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


MANIFEST: dict[str, Any] = {
    "api_version": "aidd.sciminer/remote-tool.v1",
    "kind": "RemoteTool",
    "metadata": {
        "slug": "remote-pocket-demo",
        "name": "Remote Pocket Demo",
        "version": "1.0.0",
        "description": "Minimal self-registering Remote Tool v1 demo service.",
    },
    "artifacts": {
        "inputs": [
            {"name": "protein", "type": "protein_structure@1", "required": True},
        ],
        "outputs": [
            {
                "name": "pocket",
                "type": "binding_pocket@1",
                "cardinality": "one",
                "required": True,
            },
        ],
    },
    "parameters_schema": {
        "type": "object",
        "properties": {
            "threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.5,
                "description": "Demo threshold parameter.",
            },
        },
        "additionalProperties": False,
    },
    "endpoints": {
        "invoke": "/invoke",
        "status": "/runs/{remote_run_id}",
        "logs": "/runs/{remote_run_id}/logs",
        "cancel": "/runs/{remote_run_id}/cancel",
        "artifacts": "/runs/{remote_run_id}/artifacts",
        "examples": "/examples",
        "health": "/health",
    },
    "capabilities": {"async": True, "logs": True, "cancel": True, "progress": True},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_run(app: FastAPI, remote_run_id: str) -> dict[str, Any]:
    run = app.state.runs.get(remote_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="remote run not found")
    return run


def _result_payload(remote_run_id: str) -> dict[str, Any]:
    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "pocket": {
                "name": "Demo pocket",
                "type": "binding_pocket@1",
                "files": {
                    "residue_pocket_pdb": {
                        "path": "artifacts/pocket/residue_pocket.pdb",
                        "url": f"/runs/{remote_run_id}/files/residue_pocket.pdb",
                        "sha256": _sha256(RESIDUE_POCKET_BYTES),
                        "content_type": "chemical/x-pdb",
                    },
                },
                "metadata": {"source_protein_ref": "input:protein"},
            },
        },
        "relations": [],
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Remote Tool v1 Template", version="1.0.0")
    app.state.runs = {}

    @app.get("/.well-known/sciminer-tool.json")
    async def get_manifest() -> dict[str, Any]:
        return MANIFEST

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": MANIFEST["metadata"]["slug"]}

    @app.get("/examples")
    async def examples() -> dict[str, Any]:
        return {
            "examples": [
                {
                    "name": "default",
                    "smoke": True,
                    "parameters": {"threshold": 0.5},
                    "input_artifacts": {
                        "protein": {
                            "type": "protein_structure@1",
                            "metadata": {"chain_ids": ["A"]},
                            "files": {
                                "structure_file": {
                                    "filename": "protein.pdb",
                                    "content_type": "chemical/x-pdb",
                                    "url": "/examples/default/protein.pdb",
                                    "sha256": _sha256(PROTEIN_EXAMPLE_BYTES),
                                },
                            },
                        },
                    },
                },
            ],
        }

    @app.get("/examples/default/protein.pdb")
    async def example_protein() -> Response:
        return Response(content=PROTEIN_EXAMPLE_BYTES, media_type="chemical/x-pdb")

    @app.post("/invoke")
    async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
        remote_run_id = f"run-{uuid4().hex[:12]}"
        app.state.runs[remote_run_id] = {
            "request_id": payload.get("request_id"),
            "payload": payload,
            "poll_count": 0,
            "status": "queued",
            "logs": [
                {"timestamp": _now_iso(), "level": "INFO", "message": "run accepted"},
            ],
        }
        return {"remote_run_id": remote_run_id, "status": "queued"}

    @app.get("/runs/{remote_run_id}")
    async def status(remote_run_id: str) -> dict[str, Any]:
        run = _get_run(app, remote_run_id)
        if run["status"] == "canceled":
            return {"remote_run_id": remote_run_id, "status": "canceled", "progress": 0}

        run["poll_count"] += 1
        if run["poll_count"] == 1:
            run["status"] = "running"
            return {
                "remote_run_id": remote_run_id,
                "status": "running",
                "phase": "demo_inference",
                "progress": 50,
                "message": "Demo model is running",
            }

        run["status"] = "success"
        return {
            "remote_run_id": remote_run_id,
            "status": "success",
            "progress": 100,
            "message": "Demo result is ready",
        }

    @app.get("/runs/{remote_run_id}/logs")
    async def logs(remote_run_id: str, cursor: str | None = None) -> dict[str, Any]:
        run = _get_run(app, remote_run_id)
        return {"items": run["logs"], "next_cursor": None, "has_more": False}

    @app.get("/runs/{remote_run_id}/artifacts")
    async def artifacts(remote_run_id: str) -> dict[str, Any]:
        _get_run(app, remote_run_id)
        return _result_payload(remote_run_id)

    @app.get("/runs/{remote_run_id}/files/residue_pocket.pdb")
    async def result_file(remote_run_id: str) -> Response:
        _get_run(app, remote_run_id)
        return Response(content=RESIDUE_POCKET_BYTES, media_type="chemical/x-pdb")

    @app.post("/runs/{remote_run_id}/cancel")
    async def cancel(remote_run_id: str) -> dict[str, Any]:
        run = _get_run(app, remote_run_id)
        run["status"] = "canceled"
        run["logs"].append({"timestamp": _now_iso(), "level": "WARNING", "message": "run canceled"})
        return {"remote_run_id": remote_run_id, "status": "canceled"}

    return app


app = create_app()
