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


class TASK_STATUS(_StringEnum):
    """任务状态（单一源）。

    与《03-系统架构设计说明书》3.4 节状态机一致：
    CREATED -> REJECTED: 配额/参数校验失败
    CREATED -> QUEUED -> RUNNING -> SUCCESS / FAILURE / CANCELED / TIMEOUT

    - PENDING：已创建但尚未入队调度（对应文档里的 CREATED）
    - REJECTED：准入被拒（配额不足、参数校验失败），从未进入队列
    - QUEUED：已入队/资源不足重新排队，等待调度
    - RUNNING：执行中
    - SUCCESS / FAILURE / CANCELED / TIMEOUT：终态

    注意：``REJECTED`` 是终态，但**不核销算力占用**（docs/03 §7.3、
    docs/04 §6.2：终态（含 FAILED/CANCELLED/TIMEOUT）一律核销，REJECTED
    不核销）。它记的是「这次提交被拒过」，不是一个跑过又结束的作业。

    历史沿革：本类原先定义在 ``app/models/tasks.py``，只有前端枚举 codegen
    之外的地方用它，导致 ``TaskStatus`` 扩成八态时无人拦截前端硬编码数组。
    迁到本模块后由 ``scripts/gen_frontend_enums.py`` 生成前端常量，
    ``test/test_frontend_enum_parity.py`` 即可守护。``app.models.tasks`` 仍以
    同名 re-export，老的 ``from app.models.tasks import TaskStatus`` 不变。
    """

    PENDING = "PENDING"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TIMEOUT = "TIMEOUT"
    CANCELED = "CANCELED"


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
    #: 领域对象也要能被审计定位：导出候选集、导出结构包都不是「文件」，
    #: 记成 ``file`` 会让审计员按资源维度排查时找不到那次导出。
    CANDIDATE_SET = "candidate_set"
    STRUCTURE = "structure"
    #: 靶点删除会连带蛋白、结构、口袋与残基（领域表没有 ON DELETE CASCADE，
    #: 由 ``delete_target_cascade`` 按序显式删）。记成 ``structure`` 或 ``file``
    #: 都会让审计员按资源维度查「谁把 EGFR 删了」时找不到那条记录。
    TARGET = "target"


#: 供 schema 类型注解使用的 Literal 别名（值集合来自上面的枚举）。
ProjectStatus = Literal[PROJECT_STATUS.values()]
ProjectRole = Literal[PROJECT_ROLE.values()]
TaskPriority = Literal[TASK_PRIORITY.values()]
#: 任务状态的 Literal 别名。取名 ``TaskStatusValue`` 而不是 ``TaskStatus``，
#: 因为后者是 ``app.models.tasks`` 里 ORM 层沿用的枚举类名（对外导入路径）。
TaskStatusValue = Literal[TASK_STATUS.values()]
AssetArtifactType = Literal[ASSET_ARTIFACT_TYPE.values()]
AuditAction = Literal[AUDIT_ACTION.values()]
AuditResult = Literal[AUDIT_RESULT.values()]
ResourceType = Literal[RESOURCE_TYPE.values()]


__all__ = [
    "PROJECT_STATUS",
    "PROJECT_ROLE",
    "TASK_PRIORITY",
    "TASK_STATUS",
    "ASSET_ARTIFACT_TYPE",
    "AUDIT_ACTION",
    "AUDIT_RESULT",
    "RESOURCE_TYPE",
    "ProjectStatus",
    "ProjectRole",
    "TaskPriority",
    "TaskStatusValue",
    "AssetArtifactType",
    "AuditAction",
    "AuditResult",
    "ResourceType",
]
