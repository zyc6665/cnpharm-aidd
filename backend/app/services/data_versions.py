"""数据版本用例：追加版本行、查实体历史（docs/04 §8.3、docs/18 G-11）。

本模块是 ``data_versions`` 表**唯一**的写入入口。实体表（``compounds`` /
``proteins`` / ``datasets``）保留当前态，本模块负责在每次写入路径上追加一条历史行。
两者分工的理由见 ``app.models.versions`` 的模块 docstring。

三条规矩
--------
1. **不 commit**。``record_version`` 只 ``flush``（经由 ``begin_nested``），把提交
   时机留给调用方的用例：``upsert_compound`` / ``register_dataset`` 都是在同一事务里
   先写实体行再写版本行，若这里自己 commit，实体写入失败时会留下一条指向不存在
   实体的孤儿版本。
2. **只追加**。没有 update / delete 接口。要订正历史就追加新版本。
3. **版本号由唯一约束裁决**。``next_version`` 先算「当前最大值 + 1」，并发下两个
   写入者会算出同一个 N；``(entity_type, entity_id, version)`` 的唯一约束让其中一个
   拿到 ``IntegrityError``，``record_version`` 重算后重试一次。应用层的「先查后插」
   单独使用时在并发下必然漏判，唯一约束才是真值来源。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationException
from app.common.time import isoformat_utc
from app.models.users import User
from app.models.versions import (
    ENTITY_TYPE_COMPOUND,
    ENTITY_TYPE_DATASET,
    ENTITY_TYPE_PROTEIN,
    ENTITY_TYPES,
    SOURCE_TYPE_MANUAL,
    SOURCE_TYPES,
    DataVersion,
)

logger = logging.getLogger(__name__)

#: 单个实体历史的最大页长。历史行是冷数据，但一次拉全量会让响应体失控。
MAX_PAGE_SIZE = 500


def content_hash_of(payload: Any) -> str:
    """返回内容快照的 sha256 hex。

    ``payload`` 可以是 dict / list / str / bytes：非 ``bytes`` 一律先做**稳定序列化**
    （``sort_keys=True`` + ``ensure_ascii=False``）再算哈希，否则同一份内容因键序不同
    会得到两个哈希，「两版是否真的不同」就答不准。

    **判等口径与 "值可落库" 绑定**：这里用 ``allow_nan=False``。``float('nan')``
    经默认 ``json.dumps`` 会写成 ``NaN`` 字面量，而那不是合法 JSON——PostgreSQL 的
    ``jsonb`` 直接拒收（``Token "NaN" is invalid``），SQLite 却静默存下，于是「同一份
    内容在两种库上一种能写、一种报错」。把它挡在算哈希这一步，是为了让报错发生在
    调用方看得懂的层（``ValidationException``），而不是等 ORM flush 时抛一个
    "数据库返回的错"。
    """
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        try:
            raw = json.dumps(
                payload, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False
            ).encode("utf-8")
        except ValueError as exc:
            raise ValidationException(
                "内容快照包含 NaN 或 Infinity，无法作为可复现的 JSON 快照落库"
            ) from exc
    return hashlib.sha256(raw).hexdigest()


def normalize_content(content: Any) -> Any:
    """把任意 JSON-able 对象压成**只含 JSON 原生类型**的结构，供 ``JSON`` 列落库。

    走一次 ``dumps`` → ``loads`` 往返，而不是直接塞给 ORM：
    ``default=str`` 会把 ``datetime`` / ``Decimal`` / ``UUID`` / 枚举转成字符串，
    剩下的（tuple 变 list、非字符串键变字符串）由 JSON 编解码器规范化。不做这一步，
    同一个 ``content`` 在 SQLite（存文本）与 PostgreSQL（JSONB）下可能落成不同的
    形态，之后按字段 diff 时会出现「同一次写入，两种取值」。

    已经是 ``str`` / ``bytes`` 的内容（调用方直接传了一段原文）按 JSON 字符串落库：
    ``JSON`` 列存裸文本会被双重编码，读回来就不是原文了。

    同样用 ``allow_nan=False``：NaN / Infinity 不是合法 JSON。放进来会得到两种后果
    ——PostgreSQL 的 ``jsonb`` 拒收（``Token "NaN" is invalid``）、SQLite 静默存下，
    于是同一份内容在两种库上一种能写一种报错，而生产是前者、测试是后者。
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    try:
        return json.loads(
            json.dumps(content, ensure_ascii=False, default=str, allow_nan=False)
        )
    except ValueError as exc:
        raise ValidationException(
            "内容快照包含 NaN 或 Infinity，无法作为可复现的 JSON 快照落库"
        ) from exc


def _operator_of(user: User | None) -> str | None:
    """把用户压成 ``operator`` 快照（username / email，见 docs/04 §3 note 1）。

    ``users`` 表没有 ``username`` 列，``email`` 是唯一稳定的业务标识，故优先取
    ``email``，其次 ``display_name``，都没有时留空（不写 ``anonymous`` 冒充一个
    真实操作者）。
    """
    if user is None:
        return None
    email = getattr(user, "email", None)
    if email:
        return str(email)[:64]
    display_name = getattr(user, "display_name", None)
    if display_name:
        return str(display_name)[:64]
    return None


async def next_version(db: AsyncSession, *, entity_type: str, entity_id: str) -> int:
    """返回该实体下一个可用版本号（从 1 开始）。

    首个版本的 ``MAX(version)`` 是 ``NULL``，故空表时返回 1 而不是 0。
    """
    current = await db.scalar(
        select(func.max(DataVersion.version)).where(
            DataVersion.entity_type == entity_type,
            DataVersion.entity_id == str(entity_id),
        )
    )
    return int(current or 0) + 1


async def record_version(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    source_type: str,
    user: User | None = None,
    source_file_urn: str | None = None,
    change_summary: str | None = None,
    content: Any = None,
    content_hash: str | None = None,
    version: int | None = None,
) -> DataVersion:
    """追加一条版本行并返回它；**不 commit**（由调用方的用例统一提交）。

    ``content_hash`` 显式给出时优先用它；否则用 ``content`` 算。两者都不给时
    ``content_hash`` 留 NULL —— 这比算一个「空内容」的哈希更诚实，调用方一看就知道
    这次没记内容指纹。

    给了 ``content`` 就同时落一份 ``content`` 快照（经 ``normalize_content`` 规范化），
    它是 ``diff`` 端点的唯一数据来源；只落哈希的话历史行不可解释（理由见
    ``app.models.versions.DataVersion`` 的 docstring）。

    并发冲突处理：``begin_nested()`` 把这行放进 SAVEPOINT，唯一约束冲突时只回滚
    这个 SAVEPOINT（外层事务与已写入的实体行不受影响），重算版本号后重试一次。
    重试仍冲突则抛出 ``IntegrityError``——此时说明竞争超出预期，静默吞掉会让版本
    序列出现空洞。
    """
    if entity_type not in ENTITY_TYPES:
        raise ValidationException(f"不支持的实体类型: {entity_type}")
    if source_type not in SOURCE_TYPES:
        raise ValidationException(f"不支持的版本来源: {source_type}")
    # 先规范化、再算哈希，两者口径必须完全一致。
    # 早期实现是「原始对象算哈希、规范化后的值落库」：于是 ``0`` 与 ``0.0``
    # 算出两个哈希（json 里是 ``0`` 与 ``0.0``）却被 diff 判为同一个值，
    # 同一个响应里 ``contentHashChanged: true`` 与 ``changes: []`` 互相打脸。
    # 现在哈希只认「最终落库的那个形态」，``contentHashChanged`` 与 ``changes``
    # 就由同一份数据推出来。
    snapshot = None if content is None else normalize_content(content)
    if content_hash is None and snapshot is not None:
        content_hash = content_hash_of(snapshot)

    entity_id = str(entity_id)
    attempt_version = version
    last_error: IntegrityError | None = None
    for _attempt in range(2):
        if attempt_version is None:
            attempt_version = await next_version(
                db, entity_type=entity_type, entity_id=entity_id
            )
        record = DataVersion(
            entity_type=entity_type,
            entity_id=entity_id,
            version=attempt_version,
            source_type=source_type,
            source_file_urn=source_file_urn,
            change_summary=change_summary,
            content_hash=content_hash,
            content=snapshot,
            operator=_operator_of(user),
        )
        try:
            async with db.begin_nested():
                db.add(record)
                await db.flush()
        except IntegrityError as exc:
            last_error = exc
            logger.info(
                "data_version conflict, retrying: type=%s id=%s version=%s",
                entity_type,
                entity_id,
                attempt_version,
            )
            # SAVEPOINT 已回滚，但失败的对象可能仍挂在 session 的 new/persistent
            # 集合里；不摘掉它，下一次 flush 会把同一个坏版本再插一遍。
            if record in db:
                db.expunge(record)
            attempt_version = None
            continue
        return record

    assert last_error is not None
    raise last_error


async def record_manual_version(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    user: User | None = None,
    change_summary: str | None = None,
    content: Any = None,
) -> DataVersion:
    """人工改动（改甲基化、手填序列等）的便捷封装：``source_type=MANUAL``。"""
    return await record_version(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        source_type=SOURCE_TYPE_MANUAL,
        user=user,
        change_summary=change_summary,
        content=content,
    )


async def list_versions(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[DataVersion], int]:
    """按版本号**倒序**返回该实体的历史（最新在前），以及总条数。

    倒序是因为调用方几乎总是先看「最近一次改了什么」；升序要翻到最后一页才有用。

    ``page`` 越界（大于 ``total_pages``）时返回空列表而**不夹取到最后一页**：
    夹取会让「第 999 页」与「第 1 页」返回同一批数据，调用方无法区分
    「你要的那页没有」和「已经到底了」；空列表 + ``total`` / ``total_pages``
    是标准分页语义，由前端决定怎么提示。
    """
    if entity_type not in ENTITY_TYPES:
        raise ValidationException(f"不支持的实体类型: {entity_type}")
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    entity_id = str(entity_id)

    conditions = (
        DataVersion.entity_type == entity_type,
        DataVersion.entity_id == entity_id,
    )
    total = await db.scalar(select(func.count()).select_from(DataVersion).where(*conditions))
    result = await db.execute(
        select(DataVersion)
        .where(*conditions)
        .order_by(DataVersion.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_project_versions(
    db: AsyncSession,
    *,
    project_id: str,
    entity_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[DataVersion], int]:
    """项目内的版本动态：本项目化合物 / 蛋白 / 数据集的版本行，最新在前。

    「属于本项目」由各实体的既有归属关系定义，不新增关联表：

    * ``COMPOUND`` — 本项目 ``candidates`` 引用到的分子（化合物是全局主数据，
      靠候选物建立项目归属，与 ``GET /compounds/{id}`` 的鉴权口径同源）；
    * ``PROTEIN`` — 本项目 ``targets`` 下的蛋白；
    * ``DATASET`` — ``datasets.project_id`` 直接指向本项目。

    三类实体 id 合在一个 ``IN`` 里过滤，是因为它们的主键同构（String(36) UUID），
    且 ``entity_type`` 已限定了语义；这样只需一次索引扫描即可翻页。
    """
    from app.models.compounds import Candidate
    from app.models.targets import Protein, Target
    from app.models.uploads import Dataset

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    project_id = str(project_id)

    compound_ids = select(Candidate.compound_id).where(
        Candidate.project_id == project_id,
        Candidate.compound_id.is_not(None),
    )
    protein_ids = (
        select(Protein.id)
        .join(Target, Target.id == Protein.target_id)
        .where(Target.project_id == project_id)
    )
    dataset_ids = select(Dataset.id).where(Dataset.project_id == project_id)

    scopes = [
        (ENTITY_TYPE_COMPOUND, compound_ids),
        (ENTITY_TYPE_PROTEIN, protein_ids),
        (ENTITY_TYPE_DATASET, dataset_ids),
    ]
    if entity_type is not None:
        if entity_type not in ENTITY_TYPES:
            raise ValidationException(f"不支持的实体类型: {entity_type}")
        scopes = [item for item in scopes if item[0] == entity_type]

    membership = or_(
        *[
            (DataVersion.entity_type == type_name) & (DataVersion.entity_id.in_(ids))
            for type_name, ids in scopes
        ]
    )
    total = await db.scalar(
        select(func.count()).select_from(DataVersion).where(membership)
    )
    result = await db.execute(
        select(DataVersion)
        .where(membership)
        .order_by(DataVersion.created_at.desc(), DataVersion.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total or 0)


def serialize_version(record: DataVersion) -> dict:
    """版本行的对外表示（camelCase，与前端既有约定一致）。

    **不含 ``content``**：列表页一次返回几十行，每行都带上完整快照会让响应体翻倍，
    而列表里只需要「哪一版、谁改的、改了没改」。要看快照用
    ``serialize_version_detail``。
    """
    return {
        "id": str(record.id),
        "entityType": record.entity_type,
        "entityId": str(record.entity_id),
        "version": int(record.version),
        "sourceType": record.source_type,
        "sourceFileUrn": record.source_file_urn,
        "changeSummary": record.change_summary,
        "contentHash": record.content_hash,
        "operator": record.operator,
        "createdAt": isoformat_utc(record.created_at),
    }


def serialize_version_detail(record: DataVersion) -> dict:
    """版本行的完整表示：在 ``serialize_version`` 之上补 ``content`` 快照。

    ``content`` 为 NULL 是**有信息量**的（该版本没记快照，比对不出字段），故原样
    返回 ``None`` 而不是换成 ``{}``。
    """
    payload = serialize_version(record)
    payload["content"] = record.content
    return payload


def serialize_version_summary(record: DataVersion) -> dict:
    """diff 响应里 ``from`` / ``to`` 两侧的版本摘要。

    故意**不含** ``content`` 本身：diff 已经把差异摊到 ``changes`` 里，再把两份完整
    快照各贴一遍，前端要么重复渲染要么干脆不用，白白撑大响应体。
    """
    return {
        "version": int(record.version),
        "createdAt": isoformat_utc(record.created_at),
        "operator": record.operator,
        "sourceType": record.source_type,
        "changeSummary": record.change_summary,
        "contentHash": record.content_hash,
    }


# ---------------------------------------------------------------------------
# 内容快照的摊平与字段级比对
# ---------------------------------------------------------------------------

#: 摊平路径的分隔符（``props.logP``）。
PATH_SEPARATOR = "."

#: 「这一侧没有这个字段」的哨兵，与「字段存在但值为 null」区分开。
MISSING = object()


def _join_path(prefix: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]" if prefix else f"[{key}]"
    return f"{prefix}{PATH_SEPARATOR}{key}" if prefix else str(key)


def flatten_content(content: Any, *, prefix: str = "") -> dict[str, Any]:
    """把嵌套快照摊平成 ``{点分路径: 标量}``，例如 ``{"props": {"logP": 0.1}}``
    → ``{"props.logP": 0.1}``。

    为什么必须摊平：``Compound.props`` 是一个装着 6 个描述符的 dict，若把整个
    ``props`` 当作一个字段比较，改一个 ``logP`` 就会报成「props 整块变了」——
    用户拿到的信息量与「有变化」两个字相同，diff 等于白做。摊平之后每条变化都
    落在可命名的字段上（``props.logP``），前端可以直接高亮某个数值。

    口径：
    * dict 逐键递归，list 逐下标递归（``path[0]``）；
    * **非顶层的空容器本身作为一个叶子**——``{"props": {}}`` 与 ``{}`` 之间
      ``props`` 这个字段确实被去掉了，若把它摊平成「什么都没有」，两份内容一个字段
      都没有，diff 就报 ``changes: []``，而哈希又因为键集不同报「变了」（同样是
      ``contentHashChanged`` 与 ``changes`` 互相打脸）。落成的叶子值就是 ``{}`` /
      ``[]`` 本身，JSON 可序列化，前端也能原样展示；
    * 顶层的空容器不产生路径（没有字段名可报，``{}`` 与 ``{}`` 本就相等）；
    * 标量原样作为叶子，不做数值归一（``1`` 与 ``1.0`` 是两条不同的取值）。
    """
    if isinstance(content, dict):
        if not content and prefix:
            return {prefix: {}}
        flattened: dict[str, Any] = {}
        for key, value in content.items():
            flattened.update(flatten_content(value, prefix=_join_path(prefix, key)))
        return flattened
    if isinstance(content, (list, tuple)):
        if not content and prefix:
            return {prefix: []}
        flattened = {}
        for index, value in enumerate(content):
            flattened.update(flatten_content(value, prefix=_join_path(prefix, index)))
        return flattened
    return {prefix: content}


def _same_leaf(left: Any, right: Any) -> bool:
    """叶子相等判定。

    三条刻意的「不等」：

    * ``True`` 与 ``1`` 在 Python 里相等，但在 JSON 快照里是两种取值（布尔 vs 数值）；
    * ``0`` 与 ``0.0`` 在 Python 里相等，但序列化后一个是 ``0``、一个是 ``0.0``，
      哈希不同。既然 ``contentHashChanged`` 会因此报「变了」，diff 也必须报变化，
      否则同一个响应里两个字段互相打脸；
    * ``NaN != NaN`` 是 IEEE 754 的定义，但快照里两版都是 NaN 时它们是**同一份内容**。
      用 ``repr`` 相等兜住这一种情况（``float('nan') == float('nan')`` 为 False，
      而 ``repr`` 都是 ``'nan'``）。NaN 现在已进不来（``allow_nan=False`` 在写入侧
      就拒收），这里只是让历史行与纯函数调用方不至于给出荒谬结论。
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, float) != isinstance(right, float):
        return False
    if isinstance(left, float) and left != left and isinstance(right, float) and right != right:
        return True
    return left == right


def diff_contents(before: Any, after: Any) -> tuple[list[dict], list[str]]:
    """比对两份内容快照，返回 ``(changes, unchanged_fields)``。

    ``changes`` 按字段路径排序，每条形如 ``{"field": "props.logP", "from": -0.0014,
    "to": 0.13}``；某一侧缺这个字段时对应值为 ``None``（新增/删除字段）。

    已知口径：**结构类型改变会被拆成两条**——``props`` 从 dict 变成标量时，
    ``props.logP`` 报「消失」、``props`` 报「新增」。摊平后没有「同一个路径换了
    容器类型」这种表达方式，拆成两条比造一个复合事件更好解释。

    任一侧为 ``None``（该版本没有内容快照）时调用方**不该调用本函数**：那不是
    「全部字段都变了」，而是「无从比对」，两者的区别必须由调用方显式表达
    （见 ``app.api.v1.compound_versions`` 的 warning 分支）。
    """
    left = flatten_content(before)
    right = flatten_content(after)

    changes: list[dict] = []
    unchanged: list[str] = []
    for field in sorted(set(left) | set(right)):
        old = left.get(field, MISSING)
        new = right.get(field, MISSING)
        if old is not MISSING and new is not MISSING and _same_leaf(old, new):
            unchanged.append(field)
            continue
        changes.append(
            {
                "field": field,
                "from": None if old is MISSING else old,
                "to": None if new is MISSING else new,
            }
        )
    return changes, unchanged


__all__ = [
    "MAX_PAGE_SIZE",
    "MISSING",
    "PATH_SEPARATOR",
    "content_hash_of",
    "diff_contents",
    "flatten_content",
    "list_project_versions",
    "list_versions",
    "next_version",
    "normalize_content",
    "record_manual_version",
    "record_version",
    "serialize_version",
    "serialize_version_detail",
    "serialize_version_summary",
]
