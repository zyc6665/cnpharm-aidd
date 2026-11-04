# backend/app/services/platform_tool_seeding.py
"""启动期幂等补齐平台必备工具。

背景 / 为什么需要这个模块
==========================
平台有一批「种子迁移」在 ``upgrade()`` 开头写::

    owner_id = _resolve_owner_id(bind)
    if owner_id is None:
        return

在「先跑迁移、后创建第一个 admin」的部署顺序下，这些迁移会**静默空转**：只把
``alembic_version`` 往前推，一行数据都不建。``20261029_01_mock_model_packages``
与 ``20261030_01_lvpocket_model_package`` 都已实测受害（后者用一次性 reseed 迁移
``20261102_01`` 补过，但任何新部署或重建库都会重演）。

本模块提供应用启动期的兜底：在 ``init_db()`` 之后按 slug 幂等补齐平台必备工具。
它不是再写一条 reseed 迁移，而是每次启动都收敛到「必备工具存在且为 published」。

设计要点
========
* **不复制 manifest**：工具定义（含 ``tool_package_manifest``）通过 ``importlib``
  加载原始迁移模块取得——lvpocket 用其 ``_tool_config()``，molp/msign/pocket2mol
  用 ``20261031_09`` 的 ``MODELS``，vina/boltz2/boltz2-affinity/therapainter/gromacs
  用各自迁移里的 ``_model()``/``_models()`` 工厂。原迁移模块都是幂等的 upsert，
  直接复用其数据，不复制任何 manifest 文本。
* **折叠后续增量**：``20261031_09`` 之后还有若干迁移原地改写了工具版本
  （``20261031_10``/``20261031_11`` 改 msign 输入与镜像、``20261101_01`` 把 molp
  换成 GPU 镜像）。如果直接拿 ``20261031_09.MODELS`` 落库会把工具**回退**到旧契约，
  因此这里再叠加这些迁移模块暴露的常量（``NEW_INPUTS`` / ``NEW_DIGEST`` /
  ``NEW_CUDA`` / ``NEW_VERSION`` / ``NEW_CHANGELOG``），保证种出来的是 head 状态。
  ``20261031_12``~``20261031_16`` 这 5 条新增工具迁移经核对没有后续增量覆盖，
  直接取各自 head 定义。新增工具定义的迁移今后若再被改写，也应同步到这里的折叠。
* **幂等判据**：按 slug 查 ``tools``；存在且 ``current_version.version``、``changelog``、
  ``config`` 与期望一致、``status='published'`` 时只记 ``existing``、不写库；任一不符
  （含版本落后、镜像 digest 漂移）则原地 UPDATE，绝不重复 INSERT。
* **owner 解析**（三级）：优先 ``settings.AIDD_SYSTEM_USER_ID``（且该用户存在）；
  否则取库里第一个 ``role='admin'`` 且 ``status='active'`` 的用户；都没有则返回
  ``{"skipped": ["no-owner"]}``，**不抛异常**——应用必须能起来。
* **共享 helper**：``apply_platform_tools(bind)`` 是同步核心，既供本模块的异步
  ``seed_platform_tools`` 通过 ``AsyncSession.run_sync`` 调用，也可供 alembic 迁移用
  ``op.get_bind()`` 直接调用（消除「迁移里再写一份 upsert」的重复）。
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.common.time import utcnow
from app.config import settings

logger = logging.getLogger(__name__)


# 迁移文件目录：backend/app/services/ -> parents[2] == backend
_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# 需幂等补齐的平台必备工具 slug（按顺序落库）。刻意不含 perf_tool：那是
# scripts/perf_seed.py 造的压测专用工具，不属于平台必备集合。
REQUIRED_TOOL_SLUGS = (
    "lvpocket-pocket-prediction",
    "molp-pc-property-prediction",
    "msign-affinity-prediction",
    "pocket2mol-pocket-ligand-generation",
    "autodock-vina-docking",
    "boltz2-structure-prediction",
    "boltz2-affinity-prediction",
    "therapainter-peptide-prediction",
    "gromacs-md",
    "gmx-mmpbsa",
)

# boltz2 两个镜像的 digest 显式常量表。值逐个核对自原始迁移（运行时不再解析
# 迁移模块的字节码常量）：
#   - boltz2-structure-prediction：
#     backend/alembic/versions/20261031_13_boltz2_tool.py:312
#       image_digest = "sha256:83dc125a83120c746c95446cf3dd1c7cb2edafdf676953b7a14543235d7462eb"
#   - boltz2-affinity-prediction：
#     backend/alembic/versions/20261031_14_boltz2_affinity_tool.py:328
#       image_digest = "sha256:d380abc44ba85c5d0decff05858bef2d203d8d6a05a399fde4ddb1a011b1ae26"
# 两值均已与本机主库（15432）中对应工具的 ToolVersion.config.image 实际 digest
# 逐一比对一致，故以此为准写死。
_HEAD_IMAGE_DIGESTS: dict[str, str] = {
    "boltz2-structure-prediction": (
        "sha256:83dc125a83120c746c95446cf3dd1c7cb2edafdf676953b7a14543235d7462eb"
    ),
    "boltz2-affinity-prediction": (
        "sha256:d380abc44ba85c5d0decff05858bef2d203d8d6a05a399fde4ddb1a011b1ae26"
    ),
}


@dataclass(frozen=True)
class PlatformToolSpec:
    """一个待补齐平台工具的完整落库定义。"""

    slug: str
    name: str
    description: str | None
    version: str
    changelog: str
    config: dict
    category: str = "model"
    provider: str = "platform"
    gpu_required: bool = True
    gpu_memory_mb: int = 0
    timeout_sec: int = 3600


# --------------------------------------------------------------------------- #
# 迁移模块加载 / 工具定义组装
# --------------------------------------------------------------------------- #
def _load_migration_module(filename: str):
    """按文件路径加载 alembic 迁移模块（只取其中的常量与纯函数，不执行 upgrade）。

    与 ``20261102_01_reseed_lvpocket_tool.py`` 的做法一致：alembic 按文件发现
    revision，这里用独立模块名再加载同一文件不会与其 revision 注册冲突。
    """
    path = _VERSIONS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"找不到迁移文件: {path}")
    module_name = "_platform_seed_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载迁移文件: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_manifest_overrides(
    config: dict,
    *,
    inputs: list[dict] | None = None,
    image_digest: str | None = None,
    cuda: str | None = None,
) -> dict:
    """在工具 config 上折叠后续迁移的原地改写，返回新 dict（不改入参）。

    覆盖了 ``20261031_10``/``20261031_11``（改 ``artifacts.inputs``、镜像 digest、
    variant 镜像）与 ``20261101_01``（改镜像 digest 与 ``runtime.cuda``）的等价变换。
    只处理 ``tool_package_manifest`` 的嵌套结构，不复制任何 manifest 文本。
    """
    cfg = copy.deepcopy(config)
    if cfg.get("type") == "k8s_job" and not cfg.get("resource_profile"):
        gpu = bool(cfg.get("gpu_required"))
        cfg["resource_profile"] = {
            "tier": "gpu" if gpu else "cpu",
            "cpu": 4,
            "memory_gb": 16 if gpu else 8,
            "gpu_required": gpu,
            "gpu_memory_gb": 8 if gpu else 0,
            "timeout_minutes": 60,
            "parallelism": 1,
        }
    image: str | None = None
    if image_digest:
        base_image = str(cfg.get("image") or "")
        if "@sha256:" in base_image:
            base_image = base_image.split("@sha256:", 1)[0]
        image = f"{base_image}@{image_digest}"
        cfg["image"] = image

    manifest = cfg.get("tool_package_manifest")
    if isinstance(manifest, dict):
        if inputs is not None:
            manifest.setdefault("artifacts", {})["inputs"] = copy.deepcopy(inputs)
        runtime = manifest.setdefault("runtime", {})
        if cuda is not None:
            runtime["cuda"] = cuda
        if image_digest and image is not None:
            artifacts = runtime.setdefault("artifacts", {})
            for slot in ("primary", "fallback"):
                entry = artifacts.get(slot)
                if isinstance(entry, dict):
                    entry["image"] = image
                    entry["image_digest"] = image_digest
            for variant in manifest.get("variants") or []:
                if isinstance(variant, dict) and variant.get("image"):
                    variant["image"] = image
                    if "image_digest" in variant:
                        variant["image_digest"] = image_digest
    return cfg


def _invoke_model_factory(
    module, factory_name: str, *, image_digest: str | None = None
) -> list[dict]:
    """调用迁移模块的 ``_model``/``_models`` 工厂，归一成 model dict 列表。

    需要显式镜像 digest 的工厂（boltz2 / boltz2-affinity）由调用方从
    ``_HEAD_IMAGE_DIGESTS`` 传入 ``image_digest``；其余无参工厂直接调用。
    工厂可能返回单个 dict 或 dict 列表。
    """
    factory = getattr(module, factory_name)
    if inspect.signature(factory).parameters:
        if image_digest is None:
            raise RuntimeError(
                f"{module.__name__}.{factory_name} 需要镜像 digest，但未在 "
                "_HEAD_IMAGE_DIGESTS 中登记"
            )
        result = factory(image_digest)
    else:
        result = factory()
    return [result] if isinstance(result, dict) else list(result)


def _lvpocket_model(module) -> dict:
    """把 lvpocket 迁移的模块级常量 + ``_tool_config()`` 归一成通用 model dict。"""
    return {
        "slug": module.SLUG,
        "name": module.TOOL_NAME,
        "description": module.DESCRIPTION,
        "version": module.VERSION,
        "changelog": "LVpocket-2 真实模型包（GPU，权重外置）",
        "config": module._tool_config(),
        "category": module.CATEGORY,
        "provider": module.PROVIDER,
        "gpu_required": True,
        "gpu_memory_mb": 8192,
        "timeout_sec": module.TIMEOUT_SEC,
    }


def _load_head_models() -> dict[str, dict]:
    """从各原始迁移模块取 head 工具定义（slug -> model dict），并折叠后续增量迁移。"""
    models: dict[str, dict] = {}

    # lvpocket：定义在模块级常量 + ``_tool_config()``。
    lvpocket_mod = _load_migration_module("20261030_01_lvpocket_model_package.py")
    models[lvpocket_mod.SLUG] = _lvpocket_model(lvpocket_mod)

    # molp / msign / pocket2mol：三条定义集中在 ``20261031_09`` 的 MODELS。
    models_mod = _load_migration_module("20261031_09_model_packages.py")
    for model in models_mod.MODELS:
        models[model["slug"]] = copy.deepcopy(model)

    # 折叠 ``20261031_09`` 之后的原地改写，保证种出来的是 head 契约而非旧契约。
    msign_v12_mod = _load_migration_module("20261031_11_msign_smiles_input.py")
    msign = models[msign_v12_mod.SLUG]
    msign["config"] = _apply_manifest_overrides(
        msign["config"],
        inputs=msign_v12_mod.NEW_INPUTS,
        image_digest=msign_v12_mod.NEW_DIGEST,
    )
    msign["version"] = msign_v12_mod.NEW_VERSION
    msign["changelog"] = msign_v12_mod.NEW_CHANGELOG

    molp_v11_mod = _load_migration_module("20261101_01_molp_pc_gpu_image.py")
    molp = models[molp_v11_mod.TOOL_SLUG]
    molp["config"] = _apply_manifest_overrides(
        molp["config"],
        image_digest=molp_v11_mod.NEW_DIGEST,
        cuda=molp_v11_mod.NEW_CUDA,
    )

    # 单工具 / 多工具迁移：直接调用各自的 model 工厂，不复制任何 manifest。
    for filename, factory_name in (
        ("20261031_12_vina_tool.py", "_model"),
        ("20261031_13_boltz2_tool.py", "_model"),
        ("20261031_14_boltz2_affinity_tool.py", "_model"),
        ("20261031_15_therapainter_tool.py", "_model"),
        ("20261031_16_gromacs_tools.py", "_models"),
    ):
        module = _load_migration_module(filename)
        image_digest = _HEAD_IMAGE_DIGESTS.get(getattr(module, "SLUG", ""))
        for model in _invoke_model_factory(
            module, factory_name, image_digest=image_digest
        ):
            models[model["slug"]] = model

    return models


def _spec_from_model(model: dict) -> PlatformToolSpec:
    """通用 spec 构造器：所有工具（含原有 4 个）统一从 model dict 生成落库定义。

    消除「lvpocket 特例分支 + 20261031_09 循环 + 增量折叠」各自拼 PlatformToolSpec
    的重复；新增工具只要产出一个同构 model dict 即可走同一路径。
    """
    config = copy.deepcopy(model["config"])
    if isinstance(config, dict) and config.get("type") == "k8s_job" and not config.get("resource_profile"):
        gpu = bool(model.get("gpu_required", True))
        config["resource_profile"] = {
            "tier": "gpu" if gpu else "cpu",
            "cpu": 4,
            "memory_gb": 16 if gpu else 8,
            "gpu_required": gpu,
            "gpu_memory_gb": 8 if gpu else 0,
            "timeout_minutes": 60,
            "parallelism": 1,
        }
    return PlatformToolSpec(
        slug=model["slug"],
        name=model["name"],
        description=model.get("description"),
        version=model["version"],
        changelog=model.get("changelog", ""),
        config=config,
        category=model.get("category", "model"),
        provider=model.get("provider", "platform"),
        gpu_required=model.get("gpu_required", True),
        gpu_memory_mb=model.get("gpu_memory_mb", 0),
        timeout_sec=model.get("timeout_sec") or config.get("timeout_sec") or 3600,
    )


_SPECS_CACHE: list[PlatformToolSpec] | None = None


def build_platform_tool_specs() -> list[PlatformToolSpec]:
    """组装平台必备工具的 head 定义（结果缓存）。

    工具定义全部来自原始迁移模块，本函数按 ``REQUIRED_TOOL_SLUGS`` 顺序挑选并
    统一走 :func:`_spec_from_model`；缺失任何 slug 直接报错而非静默少种。
    """
    global _SPECS_CACHE
    if _SPECS_CACHE is not None:
        return _SPECS_CACHE

    models = _load_head_models()
    missing = [slug for slug in REQUIRED_TOOL_SLUGS if slug not in models]
    if missing:
        raise KeyError(f"迁移里找不到这些必备工具的定义: {missing}")

    _SPECS_CACHE = [_spec_from_model(models[slug]) for slug in REQUIRED_TOOL_SLUGS]
    return _SPECS_CACHE


# --------------------------------------------------------------------------- #
# 同步核心：幂等 upsert（迁移与异步服务共用）
# --------------------------------------------------------------------------- #
def _canonical_config(raw: Any) -> str | None:
    """把库里读出的 config（可能是 dict 或 JSON 字符串）规范化成可比对字符串。"""
    parsed: Any = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(parsed, dict):
        return None
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False)


def _desired_canonical_config(config: dict) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=False)


def _user_exists(bind, user_id: str) -> bool:
    row = bind.execute(
        sa.text("SELECT 1 FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    return row is not None


def resolve_owner_id(bind) -> str | None:
    """解析工具 owner：settings 系统用户 -> 第一个 active admin -> None。"""
    system_user_id = getattr(settings, "AIDD_SYSTEM_USER_ID", None)
    if system_user_id:
        if _user_exists(bind, str(system_user_id)):
            return str(system_user_id)
        logger.warning(
            "AIDD_SYSTEM_USER_ID=%s 在 users 表中不存在，回退到第一个 active admin",
            system_user_id,
        )
    row = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' AND status = 'active' "
            "ORDER BY created_at ASC LIMIT 1"
        )
    ).first()
    return str(row[0]) if row else None


def _has_seed_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions", "users"}.issubset(names)


def _insert_tool(bind, spec: PlatformToolSpec, owner_id: str, now: datetime) -> str:
    tool_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description, "
            "category, status, is_public, provider_type, review_status, current_version_id, "
            "gpu_required, gpu_memory_mb, timeout_sec) "
            "VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, "
            ":category, 'published', true, :provider, 'not_required', :version_id, "
            ":gpu_required, :gpu_memory_mb, :timeout_sec)"
        ),
        {
            "id": tool_id,
            "now": now,
            "owner_id": owner_id,
            "name": spec.name,
            "slug": spec.slug,
            "description": spec.description,
            "category": spec.category,
            "provider": spec.provider,
            "version_id": version_id,
            "gpu_required": spec.gpu_required,
            "gpu_memory_mb": spec.gpu_memory_mb,
            "timeout_sec": spec.timeout_sec,
        },
    )
    bind.execute(
        sa.text(
            "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, "
            "changelog, config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, "
            ":version, :changelog, :config, true, false)"
        ),
        {
            "id": version_id,
            "now": now,
            "tool_id": tool_id,
            "version": spec.version,
            "changelog": spec.changelog,
            "config": json.dumps(spec.config),
        },
    )
    return tool_id


def _update_tool(
    bind,
    spec: PlatformToolSpec,
    *,
    tool_id: str,
    version_id: str | None,
    owner_id: str,
    now: datetime,
) -> None:
    version_id = version_id or str(uuid.uuid4())
    bind.execute(
        sa.text(
            "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
            "category = :category, status = 'published', is_public = true, "
            "provider_type = :provider, review_status = 'not_required', "
            "current_version_id = :version_id, gpu_required = :gpu_required, "
            "gpu_memory_mb = :gpu_memory_mb, timeout_sec = :timeout_sec, updated_at = :now "
            "WHERE id = :tool_id"
        ),
        {
            "owner_id": owner_id,
            "name": spec.name,
            "description": spec.description,
            "category": spec.category,
            "provider": spec.provider,
            "version_id": version_id,
            "gpu_required": spec.gpu_required,
            "gpu_memory_mb": spec.gpu_memory_mb,
            "timeout_sec": spec.timeout_sec,
            "now": now,
            "tool_id": tool_id,
        },
    )
    exists = bind.execute(
        sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if exists:
        bind.execute(
            sa.text(
                "UPDATE tool_versions SET version = :version, changelog = :changelog, "
                "config = :config, is_active = true, deprecated = false, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "id": version_id,
                "version": spec.version,
                "changelog": spec.changelog,
                "config": json.dumps(spec.config),
                "now": now,
            },
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, "
                "changelog, config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, "
                ":version, :changelog, :config, true, false)"
            ),
            {
                "id": version_id,
                "now": now,
                "tool_id": tool_id,
                "version": spec.version,
                "changelog": spec.changelog,
                "config": json.dumps(spec.config),
            },
        )


def _is_up_to_date(bind, spec: PlatformToolSpec, tool_row) -> bool:
    """工具已存在时判断是否与期望（version/changelog/config/status）一致。"""
    current_version_id, status = tool_row[1], tool_row[2]
    if status != "published" or not current_version_id:
        return False
    row = bind.execute(
        sa.text(
            "SELECT version, changelog, config FROM tool_versions WHERE id = :id"
        ),
        {"id": str(current_version_id)},
    ).first()
    if row is None:
        return False
    version, changelog, raw_config = row[0], row[1], row[2]
    if version != spec.version or changelog != spec.changelog:
        return False
    return _canonical_config(raw_config) == _desired_canonical_config(spec.config)


def apply_platform_tools(bind, *, owner_id: str | None = None) -> dict:
    """同步核心：按 slug 幂等补齐平台必备工具。

    ``bind`` 接受 SQLAlchemy ``Connection``（alembic 的 ``op.get_bind()`` 或
    ``AsyncSession.run_sync`` 里 ``session.connection()`` 都满足）。
    返回 ``{"created": [...], "existing": [...], "skipped": [...]}``；不自行 commit，
    事务由调用方负责。
    """
    if not _has_seed_tables(bind):
        return {"created": [], "existing": [], "skipped": ["no-tables"]}

    resolved_owner = owner_id or resolve_owner_id(bind)
    if resolved_owner is None:
        # 还没有任何 admin：应用必须能起来，静默跳过（返回结果而非抛异常）。
        logger.info("平台工具 seeding 跳过：库里还没有 active admin（no-owner）")
        return {"created": [], "existing": [], "skipped": ["no-owner"]}

    created: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []
    now = utcnow()

    for spec in build_platform_tool_specs():
        row = bind.execute(
            sa.text(
                "SELECT id, current_version_id, status FROM tools WHERE slug = :slug"
            ),
            {"slug": spec.slug},
        ).first()
        if row is None:
            _insert_tool(bind, spec, resolved_owner, now)
            created.append(spec.slug)
            continue
        if _is_up_to_date(bind, spec, row):
            existing.append(spec.slug)
            continue
        # 已存在但版本/契约落后：原地更新，不重复建行。
        _update_tool(
            bind,
            spec,
            tool_id=str(row[0]),
            version_id=str(row[1]) if row[1] else None,
            owner_id=resolved_owner,
            now=now,
        )
        existing.append(spec.slug)

    return {"created": created, "existing": existing, "skipped": skipped}


# --------------------------------------------------------------------------- #
# 异步入口 / 启动期入口
# --------------------------------------------------------------------------- #
async def seed_platform_tools(db, *, owner_id: str | None = None) -> dict:
    """异步入口：``db`` 为 ``AsyncSession``。

    通过 ``AsyncSession.run_sync`` 复用同步核心（同一连接、同一事务）。不 commit，
    由调用方决定事务边界。
    """

    def _work(sync_session) -> dict:
        return apply_platform_tools(
            sync_session.connection(), owner_id=owner_id
        )

    return await db.run_sync(_work)


async def seed_platform_tools_on_startup() -> dict | None:
    """应用启动期调用：按开关执行一次 seeding，失败只记日志、绝不阻断启动。

    返回 seeding 结果；开关关闭时返回 ``None``。
    """
    if not getattr(settings, "SEED_PLATFORM_TOOLS_ON_STARTUP", True):
        logger.info(
            "SEED_PLATFORM_TOOLS_ON_STARTUP=false，跳过启动期平台工具 seeding"
        )
        return None

    # 延迟导入，避免本模块被 alembic 迁移单独加载时连带创建数据库引擎。
    from app.database.session import async_session_factory

    try:
        async with async_session_factory() as db:
            result = await seed_platform_tools(db)
            await db.commit()
        logger.info("平台工具 seeding 完成: %s", result)
        return result
    except Exception:  # noqa: BLE001 - 启动期兜底绝不能把应用拖垮
        logger.exception("平台工具 seeding 失败（启动继续）")
        return None
