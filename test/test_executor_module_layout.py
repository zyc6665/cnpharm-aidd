def test_builtin_executor_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import BuiltinExecutor as LegacyBuiltinExecutor
    from app.tasks.executors.builtin import BuiltinExecutor

    assert LegacyBuiltinExecutor is BuiltinExecutor


def test_executor_errors_have_a_shared_base_module_and_legacy_imports():
    from app.tasks.executor import GPUAllocationFailed as LegacyGPUAllocationFailed
    from app.tasks.executor import TaskExecutionError as LegacyTaskExecutionError
    from app.tasks.executors.errors import GPUAllocationFailed, TaskExecutionError

    assert LegacyTaskExecutionError is TaskExecutionError
    assert LegacyGPUAllocationFailed is GPUAllocationFailed


def test_base_executor_has_a_shared_module_and_legacy_import():
    from app.tasks.executor import BaseExecutor as LegacyBaseExecutor
    from app.tasks.executors.base import BaseExecutor

    assert LegacyBaseExecutor is BaseExecutor
