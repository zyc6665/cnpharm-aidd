"""Runtime registry tests for the managed execution gateway."""

from app.execution.service import ExecutionService


def test_execution_runtime_can_be_replaced_for_worker_injection():
    from app.execution.runtime import configure_execution_service, get_execution_service

    original = get_execution_service()
    replacement = ExecutionService({"k8s_job": object()})
    try:
        configure_execution_service(replacement)
        assert get_execution_service() is replacement
    finally:
        configure_execution_service(original)
