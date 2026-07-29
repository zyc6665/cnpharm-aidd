from pathlib import Path

import yaml


def test_production_compose_contains_required_internal_services():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    for service in ("backend", "postgres", "redis", "minio", "celery-worker", "celery-worker-gpu"):
        assert service in services
    assert "volumes" not in services["backend"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert services["backend"]["healthcheck"]["test"][-1].endswith("/api/v1/system/health")


def test_production_workers_consume_backend_routed_queues():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    worker_command = compose["services"]["celery-worker"]["command"]
    gpu_worker_command = compose["services"]["celery-worker-gpu"]["command"]

    for queue in ("default", "tool_tasks", "high_priority", "cpu_queue", "maintenance", "monitoring"):
        assert queue in worker_command
    assert "gpu_queue" in gpu_worker_command


def test_ci_validates_and_builds_production_compose():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["production-compose"]
    environment = job["env"]
    required_variables = {
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "JWT_SECRET_KEY",
        "SETTINGS_ENCRYPTION_KEY",
        "CORS_ORIGINS",
    }
    commands = [step.get("run", "") for step in job["steps"]]

    assert required_variables <= environment.keys()
    assert all(environment[name] for name in required_variables)
    assert any(
        "docker compose -f docker-compose.prod.yml config --quiet" in command
        for command in commands
    )
    assert any(
        "docker compose -f docker-compose.prod.yml build backend" in command
        for command in commands
    )
