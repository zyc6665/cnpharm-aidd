"""项目配额 API（docs/05 §3 ``/projects/{id}/quota``、§9 ``/compute/quota``）。

两个 router 的分工与 targets/compounds/datasets 一致：

- ``project_router``（无 prefix，注册时挂 ``/projects``）：单项目的配额读写；
- ``router``（无 prefix，注册时挂 ``/compute``）：当前用户的跨项目配额汇总。

权限口径
--------
读用 ``READ_ROLES``（四种成员都能看自己的额度，否则「为什么提交被拦」无法自查）；
写只给 ``owner``——配额是项目级的一等配置，能改它就能影响全部成员能不能提交任务，
与 ``projects.py`` 里归档/删除同属 owner 级动作（``editor`` 能改项目名与目标，
但改不了「这个项目能用多少算力」）。

领域逻辑全在 ``app.services.project_quotas``，本模块只做权限、HTTP 语义与响应包装。

读写不对称
----------
只有 ``PUT`` 会写库。``GET`` 是**纯读**：没有配额记录时返回默认值 + ``configured=false``，
绝不顺手建记录——否则「有没有人点开过配额页」会改变这个项目能不能提交任务
（详见 ``get_project_quota`` 与 ``_quota_payload`` 的说明）。

错误码
------
``docs/05`` §12 的 ``40303``（配额不足）业务码**未实现**：仓内 ``AppException``
没有业务码透传机制，现有 403/422 都是裸 code，为一个端点单独引入一套业务码是
另一件事。当前用 ``429`` + ``detail.dimension``（``maxConcurrentDcu`` /
``maxConcurrentCpuTasks`` / ``dailyQuotaMinutes``）表达，待 ``AppException``
支持业务码后统一。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.quotas import DEFAULT_QUOTA_PERIOD
from app.models.users import User
from app.schemas.quotas import ProjectQuotaUpdate
from app.services import project_quotas as quota_service
from app.services.project_access import require_project_role

_FEATURE_FLAG = Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))

#: 项目内读角色（docs/04 §3 角色矩阵）。
READ_ROLES = ("owner", "editor", "runner", "viewer")
#: 项目内写角色：配额属于算力分配，只有 owner 能定。
WRITE_ROLES = ("owner",)

project_router = APIRouter(dependencies=[_FEATURE_FLAG])
router = APIRouter(dependencies=[_FEATURE_FLAG])


async def _quota_payload(db: AsyncSession, *, project_id: str) -> dict:
    """读配额 + 用量 + 当前占用，拼成统一响应体。

    **只读，绝不建记录**：``load_project_quota`` 返回 ``None`` 时用默认值拼一个
    「未落库」的响应体（``configured=False``）。若这里改回
    ``get_or_create_project_quota``，那么「有没有人点开过配额页」就会改变这个项目
    能不能提交任务——前端在项目总览挂一张配额卡片，所有存量项目打开首页那一刻
    就被静默套上「并发 2 张 DCU」，而提交被拦的人完全无从知道原因。
    回归防线：``test_get_quota_does_not_create_a_row`` 与
    ``test_get_quota_does_not_change_submission_behaviour``。
    """
    quota = await quota_service.load_project_quota(db, project_id=project_id)
    # 未配置时按默认周期统计用量：没有记录就没有「管理员选的周期」，用默认值。
    period = quota.quota_period if quota is not None else DEFAULT_QUOTA_PERIOD
    usage = await quota_service.project_usage_minutes(
        db, project_id=project_id, period=period
    )
    active = await quota_service.project_active_counts(db, project_id=project_id)
    if quota is None:
        return quota_service.serialize_default_quota(
            project_id=project_id, usage=usage, active=active
        )
    return quota_service.serialize_quota(quota, usage=usage, active=active)


@project_router.get("/{project_id}/quota", response_model=dict)
async def get_project_quota(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询项目配额与本期已用算力分钟。

    **纯读操作，不创建配额记录。** 没有记录时返回默认值，并用
    ``configured=false``（与 ``updatedAt=null``）标明「这个项目还没配过」。

    这个区分是必须的，不是锦上添花：``check_submission_allowed`` 里
    「没有记录 = 不限」，而默认值里 ``max_concurrent_dcu=2`` 是**生效的**
    ——如果 GET 顺手落一条记录，那么「有没有人点开过配额页」就会决定这个项目
    能不能提交任务：前端挂一张配额卡片，存量项目打开首页那一刻就被静默套上
    「并发 2 张 DCU」，提交被拦时用户看不到任何线索。

    所以：**配额的唯一写入入口是 ``PUT``**。要让默认值生效，得显式 PUT 一次
    （前端「使用默认配额」按钮 = 把默认值 PUT 上来）。
    """
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=READ_ROLES,
    )
    return success_response(data=await _quota_payload(db, project_id=project_id))


@project_router.put("/{project_id}/quota", response_model=dict)
async def set_project_quota(
    project_id: str,
    data: ProjectQuotaUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设置项目配额（部分更新：只改传入的字段）。

    这是配额**唯一的写入入口**：``PUT`` 才会真正落库。项目从来没有配额记录时，
    这里先按默认值建行再改字段；因此「提交一份空 body」等于「显式采用默认配额」，
    而当前的空 body 会被 schema 拒绝（422）——要显式采用默认值，就把默认值原样
    PUT 上来。

    同时接受 camelCase 与 snake_case 字段名（见 ``app.schemas.quotas``）。
    ``overdraft_ratio`` 低于 1.00 或各计数为负时服务层抛
    ``ValidationException``（422），不会留下「改了一半」的配额。

    校验**先于** ``get_or_create``：否则一次被 422 拒绝的 PUT 会顺手建出一条
    默认配额记录，请求失败却产生副作用（而默认记录本身就带着 2 并 DCU 的上限）。
    """
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=WRITE_ROLES,
    )
    changes = quota_service.validate_quota_changes(**data.model_dump(exclude_unset=True))
    quota = await quota_service.get_or_create_project_quota(
        db, project_id=project_id, created_by=str(current_user.id)
    )
    await quota_service.update_project_quota(
        db,
        quota=quota,
        updated_by=str(current_user.id),
        **changes,
    )
    return success_response(
        data=await _quota_payload(db, project_id=project_id), message="项目配额已更新"
    )


@router.get("/quota", response_model=dict)
async def get_compute_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的跨项目配额汇总（docs/05 §9）。

    只看**有配额记录**的项目：没配 = 不限，把不限项目的历史用量加进来会让
    ``exceeded`` 变得没有意义。字段口径见
    ``app.services.project_quotas.user_quota_summary``。
    """
    return success_response(
        data=await quota_service.user_quota_summary(db, user_id=str(current_user.id))
    )


__all__ = ["READ_ROLES", "WRITE_ROLES", "project_router", "router"]
