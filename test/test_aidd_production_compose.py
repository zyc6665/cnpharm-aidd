"""AIDD offline and production deployment contract tests."""

from pathlib import Path

import yaml

from app.config import Settings


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_compose(filename: str) -> dict:
    return yaml.safe_load((ROOT_DIR / filename).read_text(encoding="utf-8"))


def test_production_compose_uses_postgres_redis_and_minio_with_health_gates() -> None:
    """生产部署必须使用 PostgreSQL、Redis 和 MinIO，并以健康检查阻塞应用启动。"""
    compose = _load_compose("deploy/compose/docker-compose.prod.yml")
    services = compose["services"]

    backend_environment = services["backend"]["environment"]
    assert "sqlite" not in backend_environment["DATABASE_URL"].lower()
    assert backend_environment["STORAGE_BACKEND"] == "minio"
    assert backend_environment["CACHE_BACKEND"] == "redis"
    assert backend_environment["TASK_EXECUTION_BACKEND"] == "celery"

    for service_name in ("postgres", "redis", "minio"):
        service = services[service_name]
        assert service.get("healthcheck"), f"{service_name} must define a healthcheck"
        assert service.get("volumes"), f"{service_name} must persist data"

    assert (
        "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
        == services["postgres"]["environment"]["POSTGRES_PASSWORD"]
    )
    assert "${REDIS_PASSWORD:?set REDIS_PASSWORD}" in services["redis"]["command"]
    assert (
        "${MINIO_ROOT_PASSWORD:?set MINIO_ROOT_PASSWORD}"
        == services["minio"]["environment"]["MINIO_ROOT_PASSWORD"]
    )

    for service_name in ("backend", "celery-worker", "celery-worker-heavy", "celery-worker-gpu"):
        dependencies = services[service_name]["depends_on"]
        for dependency in ("postgres", "redis", "minio"):
            assert dependencies[dependency]["condition"] == "service_healthy"


def test_production_compose_does_not_mount_host_docker_socket() -> None:
    """生产 API 和 Worker 容器不得挂载宿主机 Docker Socket。"""
    compose = _load_compose("deploy/compose/docker-compose.prod.yml")

    for service_name in ("backend", "celery-worker", "celery-worker-gpu"):
        volumes = compose["services"][service_name].get("volumes", [])
        assert all("/var/run/docker.sock" not in str(volume) for volume in volumes)


def test_aidd_development_compose_provides_local_stateful_services() -> None:
    """AIDD 开发 Compose 应提供本地 PostgreSQL、Redis、MinIO 基础设施。"""
    compose = _load_compose("deploy/compose/docker-compose.dev.yml")
    services = compose["services"]

    for service_name in (
        "postgres",
        "redis",
        "minio",
        "backend",
        "celery-worker",
        "celery-worker-heavy",
    ):
        assert service_name in services

    backend_environment = services["backend"]["environment"]
    assert backend_environment["DATABASE_URL"].startswith("postgresql+asyncpg://")
    assert backend_environment["STORAGE_BACKEND"] == "minio"
    assert backend_environment["CACHE_BACKEND"] == "redis"
    assert backend_environment["TASK_EXECUTION_BACKEND"] == "celery"


def test_offline_deployment_guide_covers_domestic_gpu_and_dcu_boundaries() -> None:
    """离线部署文档必须说明信创、NVIDIA 和海光 DCU 的上线边界。"""
    guide = (ROOT_DIR / "docs/archive-upstream/guides/aidd-offline-deployment.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "麒麟",
        "UOS",
        "海光 x86_64",
        "NVIDIA GPU",
        "海光 DCU",
        "adapted_pending_hardware_validation",
        "deploy/compose/docker-compose.prod.yml",
        "MinIO",
        "PostgreSQL",
        "Redis",
    ]

    for term in required_terms:
        assert term in guide


def test_production_settings_reject_local_runtime_backends() -> None:
    """生产配置不得退回 SQLite、本地文件存储、内存缓存或直连执行。"""
    base_kwargs = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "CORS_ORIGINS": ["https://sciminer.example.com"],
        "JWT_SECRET_KEY": "j" * 32,
        "SETTINGS_ENCRYPTION_KEY": "e" * 32,
        "DATABASE_URL": "postgresql+asyncpg://scitool:secret@postgres:5432/scitool",
        "STORAGE_BACKEND": "minio",
        "MINIO_ENDPOINT": "minio:9000",
        "MINIO_ACCESS_KEY": "minio-user",
        "MINIO_SECRET_KEY": "minio-password",
        "CACHE_BACKEND": "redis",
        "REDIS_HOST": "redis",
        "REDIS_PASSWORD": "redis-password",
        "CELERY_BROKER_URL": "redis://:redis-password@redis:6379/1",
        "CELERY_RESULT_BACKEND": "redis://:redis-password@redis:6379/2",
        "TASK_EXECUTION_BACKEND": "celery",
    }
    Settings(**base_kwargs)

    invalid_overrides = [
        (
            "DATABASE_URL",
            "sqlite+aiosqlite:///./storage/scitool.db",
            "DATABASE_URL must use PostgreSQL",
        ),
        ("STORAGE_BACKEND", "local", "STORAGE_BACKEND must be minio"),
        ("CACHE_BACKEND", "memory", "CACHE_BACKEND must be redis"),
        ("REDIS_PASSWORD", "", "REDIS_PASSWORD must be configured"),
        ("CELERY_BROKER_URL", None, "CELERY_BROKER_URL must be configured"),
        ("TASK_EXECUTION_BACKEND", "direct", "TASK_EXECUTION_BACKEND must be celery"),
    ]

    for key, value, message in invalid_overrides:
        kwargs = dict(base_kwargs)
        kwargs[key] = value
        try:
            Settings(**kwargs)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected production settings to reject {key}")
