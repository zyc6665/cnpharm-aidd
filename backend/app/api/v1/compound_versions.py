"""化合物版本历史与版本差异（docs/05 §4 表：``/versions``、``/diff``）。

本模块只做**读**：版本行由实体写入路径在各自事务里追加
（``domain_compounds.upsert_compound`` 等，见 ``app.services.data_versions``），
这里不提供写入端点——历史一旦可从 HTTP 侧改写，「只追加」这条规矩就在最后一层断了。

为什么单独开一个模块，而不是塞进 ``api/v1/compounds.py``
------------------------------------------------------
1. ``compounds.py`` 已经有 777 行、且**两个** APIRouter（``project_router`` 带
   ``/projects`` 前缀 + 无前缀的 ``router``）。再往里加两个只属于 ``router`` 的端点，
   读代码的人必须先在脑里核对「这条路径会不会被前缀吃掉」，而这类前缀错误
   在测试里表现为 404，排查成本远高于它省下的那一行注册。
2. 差异对比是**算法**（快照摊平 + 字段级比对，见
   ``data_versions.flatten_content`` / ``diff_contents``），不是「再查一次库」。
   它需要的上下文（有向 diff、无快照时的降级口径）与化合物 CRUD 无关，
   混在一起会让 compounds.py 的模块 docstring（讲的是项目空间与候选物）失焦。
3. 独立模块的代价只有 ``api/v1/__init__.py`` 里的一行注册，比上面两条便宜。

路径前缀：本模块的 ``router`` 无 prefix，路由里写全 ``/compounds/...``，与
``compounds.router`` 注册方式一致（同一份 ``AIDD_PROJECT_WORKSPACE_ENABLED``
功能开关，开关关掉时这两个端点与化合物详情一起消失，不会出现「详情没有、历史还在」）。

三个口径决定（理由写在各自函数里，这里只列结论）
------------------------------------------------
* **权限**：复用 ``domain_compounds.require_compound_read_access``——与
  ``GET /compounds/{id}`` 同一份实现，不可见一律 404，不泄露存在性。
* **无内容快照**：返回 ``changes: []`` 加 ``warning``，不报 409/422。历史版本是
  既成事实，报错的唯一效果是让用户去「修改历史」，而历史不可修改。
* **``from`` 晚于 ``to``**：按请求方向比对，不排序、不报错。diff 本身是有向的，
  「从第 3 版回到第 1 版会改动什么」是一个有意义的问题（回滚前确认）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.exceptions import NotFoundException
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.users import User
from app.models.versions import ENTITY_TYPE_COMPOUND, DataVersion
from app.services import data_versions as versions_service
from app.services import domain_compounds

_FEATURE_FLAG = Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))

router = APIRouter(dependencies=[_FEATURE_FLAG])

#: 版本历史页长：默认 20、上限 100。历史行带不了几条就得翻页，但一次拉 500 行
#: （服务层上限 ``MAX_PAGE_SIZE``）对前端表格没有意义，故接口层单独收紧。
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


async def _load_version(
    db: AsyncSession, *, compound_id: str, version: int
) -> DataVersion:
    """按版本号取一行；不存在时 404（与「化合物不存在」同一口径，不区分原因）。"""
    record = await db.scalar(
        select(DataVersion).where(
            DataVersion.entity_type == ENTITY_TYPE_COMPOUND,
            DataVersion.entity_id == str(compound_id),
            DataVersion.version == int(version),
        )
    )
    if record is None:
        raise NotFoundException(f"化合物第 {version} 版不存在")
    return record


def _snapshot_warning(
    *,
    before: DataVersion,
    after: DataVersion,
) -> str | None:
    """两侧快照是否齐备；不齐备时返回给用户看的说明。

    分开报「哪一版缺」而不是笼统说「无法比对」：用户据此能判断是「这一版太久远」
    还是「这条写入路径没接快照」，前者只能接受，后者是缺陷该修。
    """
    missing = [
        record.version
        for record in (before, after)
        if record.content is None
    ]
    if not missing:
        return None
    versions = "、".join(f"第 {version} 版" for version in sorted(set(missing)))
    return f"{versions}未记录内容快照，无法比对字段"


@router.get("/compounds/{compound_id}/versions", response_model=dict)
async def list_compound_versions(
    compound_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """化合物的版本历史，按版本号**倒序**（最新在前）。

    倒序是因为调用方几乎总是先看「最近一次改了什么」；要看「最初长什么样」就得翻到
    最后一页，那是少数派需求。

    响应里**不含** ``content`` 快照（列表页每行都带上完整快照会让响应体翻倍）；
    要看某一版的内容用 ``GET /data-versions/COMPOUND/{id}/{version}``。
    """
    await domain_compounds.require_compound_read_access(
        db, compound_id=compound_id, user=current_user
    )
    records, total = await versions_service.list_versions(
        db,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id=compound_id,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        items=[versions_service.serialize_version(item) for item in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/compounds/{compound_id}/diff", response_model=dict)
async def diff_compound_versions(
    compound_id: str,
    from_version: int = Query(..., alias="from", ge=1, description="起始版本号"),
    to_version: int = Query(..., alias="to", ge=1, description="目标版本号"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """两个版本的字段级差异（``?from=1&to=3``）。

    ``from`` 是 Python 保留字，故参数名取 ``from_version``、用 ``alias="from"``
    保留对外契约；反过来（把参数直接叫 ``from``）在函数签名里根本写不出来。

    **diff 是有向的**：``changes[].from`` 永远是 ``?from=`` 那一版的取值、
    ``changes[].to`` 是 ``?to=`` 那一版的取值。``from=3&to=1`` 因此表示「从第 3 版
    退回第 1 版会改动什么」，是合法且有意义的查询（回滚前确认），不排序也不报错：

    * 若排序成 ``min → max``，响应里的 ``from`` 就与请求参数不一致，前端把「第 1 版」
      渲染在用户刚点的「第 3 版」上——这是最难查的一类 bug（数据对、标签错）。
    * 若返回 422，等于把「逆序对比」判成非法，用户只能自己交换参数再发一次请求；
      而 422 的报错文案又无法表达「其实反过来调就可以」。

    无内容快照时**不报错**，返回 ``changes: []`` 与 ``warning``：本次迁移之前写入的
    版本行只有哈希，那是既成事实，用户无法通过改历史来消除它（历史不可改写）。
    报 409 只会把「我们记漏了」变成「你查错了」。为了让调用方能区分
    「两版相同」和「无从比对」，``warning`` 键**总是存在**、无话可说时为 ``null``。
    """
    await domain_compounds.require_compound_read_access(
        db, compound_id=compound_id, user=current_user
    )
    before = await _load_version(db, compound_id=compound_id, version=from_version)
    after = await _load_version(db, compound_id=compound_id, version=to_version)

    warning = _snapshot_warning(before=before, after=after)
    if warning is None:
        changes, unchanged_fields = versions_service.diff_contents(
            before.content, after.content
        )
    else:
        # 缺快照 ≠ 全部字段都变了：两者的区别必须由 warning 显式表达，
        # 否则前端会把「无从比对」渲染成「一模一样」或「全变了」两种相反的谎。
        changes, unchanged_fields = [], []

    # 两侧都有 content_hash 才谈得上「是否变了」；缺一侧就给 null，而不是猜 false。
    if before.content_hash is None or after.content_hash is None:
        content_hash_changed: bool | None = None
    else:
        content_hash_changed = before.content_hash != after.content_hash

    return success_response(
        data={
            "compoundId": str(compound_id),
            "from": versions_service.serialize_version_summary(before),
            "to": versions_service.serialize_version_summary(after),
            "contentHashChanged": content_hash_changed,
            "changes": changes,
            "unchangedFields": unchanged_fields,
            "warning": warning,
        }
    )


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "router"]
