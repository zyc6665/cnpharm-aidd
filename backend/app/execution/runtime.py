"""Process-local execution Gateway registry.

Infrastructure bootstrap code configures provider adapters once per worker
process. Task code only retrieves the stable ``ExecutionService`` boundary.
"""

from __future__ import annotations

from threading import RLock

from app.execution.service import ExecutionService


_lock = RLock()
_execution_service = ExecutionService({})


def configure_execution_service(service: ExecutionService) -> None:
    """Replace the process-local Gateway used by task workers."""
    if not isinstance(service, ExecutionService):
        raise TypeError("execution service must be an ExecutionService")
    global _execution_service
    with _lock:
        _execution_service = service


def get_execution_service() -> ExecutionService:
    """Return the currently configured execution Gateway."""
    with _lock:
        return _execution_service
