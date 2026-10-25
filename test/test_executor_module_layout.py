"""Executor module layout tests."""

from pathlib import Path


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


def test_remote_api_executor_is_gone():
    """交付线禁止公网调用，远程 API 执行器及其兼容导出必须一并退场。"""
    import app.tasks.executor as executor_module

    assert not hasattr(executor_module, "RemoteAPIExecutor")
    backend_root = Path(__file__).resolve().parents[1] / "backend"
    assert not (backend_root / "app" / "tasks" / "executors" / "remote_api.py").exists()


def test_docker_security_validation_has_a_dedicated_module():
    from app.tasks.executors.docker_security import validate_docker_execution_inputs

    assert callable(validate_docker_execution_inputs)


def test_docker_output_parser_has_a_dedicated_module():
    from app.tasks.executors.docker_output import parse_docker_output

    assert callable(parse_docker_output)
    assert parse_docker_output('log\n{"score": 1}') == {"score": 1}
    assert parse_docker_output("OUTPUT_JSON: {\"score\": 2}\nignored") == {"score": 2}


def test_docker_executor_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import DockerExecutor as LegacyDockerExecutor
    from app.tasks.executors.docker import DockerExecutor

    assert LegacyDockerExecutor is DockerExecutor


def test_python_script_executor_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import PythonScriptExecutor as LegacyPythonScriptExecutor
    from app.tasks.executors.python_script import PythonScriptExecutor

    assert LegacyPythonScriptExecutor is PythonScriptExecutor


def test_executor_factory_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import TaskExecutor as LegacyTaskExecutor
    from app.tasks.executors.factory import TaskExecutor

    assert LegacyTaskExecutor is TaskExecutor


def test_ssh_job_executor_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import SSHJobExecutor as LegacySSHJobExecutor
    from app.tasks.executors.ssh_job import SSHJobExecutor

    assert LegacySSHJobExecutor is SSHJobExecutor
