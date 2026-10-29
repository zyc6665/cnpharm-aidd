# backend/app/common/enums.py
"""单一枚举源（计划 §3.1）。

本模块集中平台里"取值集合固定、且前后端共享"的枚举值，避免同一组字符串散落在
Pydantic schema、ORM 模型与前端 ``.d.ts`` 三处各写一份。每组提供两样东西：

* 一个 ``enum.Enum`` 子类（**全大写**名字，如 ``PROJECT_STATUS``），带
  ``values()`` 类方法，供 ``scripts/gen_frontend_enums.py`` 直接 import 迭代；
* 一个 ``typing.Literal`` 类型别名（CamelCase 名字，如 ``ProjectStatus``），
  供 schema 的 ``status: ProjectStatus`` 注解使用。

**字符串值本身冻结**（计划 §1）：角色仍是 ``owner/editor/runner/viewer``，
优先级仍是 ``low/normal/high``，不新增 ``bulk``。唯一的行为改动是项目状态补
``paused``（见计划 §3.1）。

审计三组（``AUDIT_ACTION`` / ``AUDIT_RESULT`` / ``RESOURCE_TYPE``）曾经直接定义在
``app/logging/audit.py``，这里迁移为单一源后由 ``app.logging.audit`` re-export 同名
类（``AuditAction = AUDIT_ACTION`` 等），因此 ``from app.logging.audit import
AuditAction`` 的老代码与 ``AuditAction.LOGIN`` 的枚举成员访问完全不变。

注意：``typing.Literal[...]`` 以 ``"...".values()``（元组）作为参数在运行时是合法的，
mypy / pyright 与 Pydantic 都能正确展开。
"""

from __future__ import annotations

import enum
from typing import Literal, Tuple

from app.artifact_standards.asset_types import ASSET_ARTIFACT_TYPES


class _StringEnum(str, enum.Enum):
    """``str`` 枚举基类，提供稳定的 ``values()`` 供内省与 codegen。"""

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        return tuple(member.value for member in cls)


class PROJECT_STATUS(_StringEnum):
    """研究项目状态。``paused`` 为本次新增（计划 §3.1）。"""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FROZEN = "frozen"
    PAUSED = "paused"


class PROJECT_ROLE(_StringEnum):
    """项目成员角色。字符串值保持不变（计划 §1：不重命名）。"""

    OWNER = "owner"
    EDITOR = "editor"
    RUNNER = "runner"
    VIEWER = "viewer"


class TASK_PRIORITY(_StringEnum):
    """任务优先级。``BULK`` 属二期，本次不引入（计划 §1）。"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


#: 数据资产根类型（Task 5 §7.1）。取值真源是
#: ``app.artifact_standards.asset_types.ASSET_ARTIFACT_TYPES``——这里用函数式 API
#: **派生**出 ``_StringEnum`` 供 ``scripts/gen_frontend_enums.py`` 迭代，避免在前端
#: 再手抄一份 8 值清单。成员名由取值大写生成（如 ``COMPOUND_SET``）。
ASSET_ARTIFACT_TYPE = _StringEnum(
    "ASSET_ARTIFACT_TYPE",
    {value.upper(): value for value in ASSET_ARTIFACT_TYPES},
)


class AUDIT_ACTION(_StringEnum):
    """审计操作类型（原 ``app.logging.audit.AuditAction``）。"""

    # 认证相关
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    TOKEN_REFRESH = "token_refresh"

    # 数据操作
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    IMPORT = "import"

    # 任务相关
    TASK_SUBMIT = "task_submit"
    TASK_CANCEL = "task_cancel"
    TASK_RETRY = "task_retry"

    # 文件相关
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"

    # 研发决策（只追加，无 UPDATE/DELETE）
    DECISION_CREATE = "decision_create"

    # 管理员操作
    ADMIN_USER_CREATE = "admin_user_create"
    ADMIN_USER_UPDATE = "admin_user_update"
    ADMIN_USER_DELETE = "admin_user_delete"
    ADMIN_CONFIG_CHANGE = "admin_config_change"
    ADMIN_TOOL_CREATE = "admin_tool_create"
    ADMIN_TOOL_UPDATE = "admin_tool_update"

    # 系统操作
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    SYSTEM_CONFIG = "system_config"


class AUDIT_RESULT(_StringEnum):
    """审计结果（原 ``app.logging.audit.AuditResult``）。"""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


class RESOURCE_TYPE(_StringEnum):
    """审计资源类型（原 ``app.logging.audit.ResourceType``）。"""

    USER = "user"
    TASK = "task"
    TOOL = "tool"
    FILE = "file"
    CONFIG = "config"
    SESSION = "session"
    SYSTEM = "system"
    DECISION_RECORD = "decision_record"


#: 供 schema 类型注解使用的 Literal 别名（值集合来自上面的枚举）。
ProjectStatus = Literal[PROJECT_STATUS.values()]
ProjectRole = Literal[PROJECT_ROLE.values()]
TaskPriority = Literal[TASK_PRIORITY.values()]
AssetArtifactType = Literal[ASSET_ARTIFACT_TYPE.values()]
AuditAction = Literal[AUDIT_ACTION.values()]
AuditResult = Literal[AUDIT_RESULT.values()]
ResourceType = Literal[RESOURCE_TYPE.values()]


__all__ = [
    "PROJECT_STATUS",
    "PROJECT_ROLE",
    "TASK_PRIORITY",
    "ASSET_ARTIFACT_TYPE",
    "AUDIT_ACTION",
    "AUDIT_RESULT",
    "RESOURCE_TYPE",
    "ProjectStatus",
    "ProjectRole",
    "TaskPriority",
    "AssetArtifactType",
    "AuditAction",
    "AuditResult",
    "ResourceType",
]
