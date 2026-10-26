"""任务执行器兼容导出。

具体执行器位于 :mod:`app.tasks.executors`，保留本模块仅用于兼容既有导入路径。
"""

from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.builtin import BuiltinExecutor
from app.tasks.executors.docker import DockerExecutor
from app.tasks.executors.errors import (
    GPUAllocationFailed,
    ResourceAdmissionFailed,
    TaskExecutionError,
    TaskTimeoutError,
)
from app.tasks.executors.factory import TaskExecutor
from app.tasks.executors.kubernetes_job import KubernetesJobExecutor
from app.tasks.executors.python_script import PythonScriptExecutor
from app.tasks.executors.ssh_job import SSHJobExecutor
from app.tasks.ssh_transport import ParamikoSSHTransport

__all__ = [
    "BaseExecutor",
    "BuiltinExecutor",
    "DockerExecutor",
    "GPUAllocationFailed",
    "KubernetesJobExecutor",
    "ParamikoSSHTransport",
    "PythonScriptExecutor",
    "ResourceAdmissionFailed",
    "SSHJobExecutor",
    "TaskExecutionError",
    "TaskExecutor",
    "TaskTimeoutError",
]
