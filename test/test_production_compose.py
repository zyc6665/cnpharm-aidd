from pathlib import Path

import yaml


def test_production_compose_contains_required_internal_services():
    compose = yaml.safe_load(Path("deploy/compose/docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    for service in (
        "backend",
        "postgres",
        "redis",
        "minio",
        "celery-worker",
        "celery-worker-heavy",
        "celery-worker-gpu",
        "celery-beat",
    ):
        assert service in services
    assert "volumes" not in services["backend"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert services["backend"]["healthcheck"]["test"][-1].endswith("/api/v1/system/health")


def test_production_workers_consume_backend_routed_queues():
    compose = yaml.safe_load(Path("deploy/compose/docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    worker_command = compose["services"]["celery-worker"]["command"]
    heavy_worker_command = compose["services"]["celery-worker-heavy"]["command"]
    gpu_worker_command = compose["services"]["celery-worker-gpu"]["command"]

    for queue in ("default", "tool_tasks", "high_priority", "cpu_queue", "maintenance", "monitoring"):
        assert queue in worker_command
    assert "heavy_compute" not in worker_command
    assert "--queues=heavy_compute" in heavy_worker_command
    assert "gpu_queue" in gpu_worker_command
    assert services["celery-worker"]["environment"]["WORKER_LISTEN_QUEUES"] == (
        "default,tool_tasks,high_priority,cpu_queue,maintenance,monitoring"
    )
    assert services["celery-worker-heavy"]["environment"]["WORKER_LISTEN_QUEUES"] == "heavy_compute"
    assert services["celery-worker-gpu"]["environment"]["WORKER_LISTEN_QUEUES"] == "gpu_queue"


def test_production_compose_enables_resource_scheduling_and_beat():
    compose = yaml.safe_load(Path("deploy/compose/docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    backend_environment = services["backend"]["environment"]
    worker_environment = services["celery-worker"]["environment"]

    for key in (
        "WORKER_CAPABILITY_ADMISSION_ENABLED",
        "WORKER_CAPABILITY_ROUTING_ENABLED",
        "WORKER_CAPABILITY_RESERVATION_ENABLED",
        "RESOURCE_SCOPE_QUOTA_ENABLED",
    ):
        assert backend_environment[key] == "true"
    assert backend_environment["TASK_CANCELLATION_STALE_AFTER_SECONDS"] == (
        "${TASK_CANCELLATION_STALE_AFTER_SECONDS:-900}"
    )
    assert backend_environment["TASK_CANCELLATION_RECONCILE_BATCH_SIZE"] == (
        "${TASK_CANCELLATION_RECONCILE_BATCH_SIZE:-100}"
    )
    assert backend_environment["WORKFLOW_RECONCILE_LOCK_TTL_SECONDS"] == (
        "${WORKFLOW_RECONCILE_LOCK_TTL_SECONDS:-60}"
    )
    assert worker_environment["WORKER_CAPABILITY_JSON"]
    assert "$${HOSTNAME}" in worker_environment["WORKER_CAPABILITY_JSON"]
    assert services["celery-beat"]["command"] == (
        "celery -A app.worker.celery_app beat --loglevel=info"
    )
    assert services["celery-beat"]["environment"]["WORKER_CAPABILITY_HEARTBEAT_QUEUES"] == (
        "default,heavy_compute,gpu_queue"
    )
    assert "celery-beat-gpu" not in services


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
        "docker compose -f deploy/compose/docker-compose.prod.yml config --quiet" in command
        for command in commands
    )
    assert any(
        "docker compose -f deploy/compose/docker-compose.prod.yml build backend" in command
        for command in commands
    )
