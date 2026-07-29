from pathlib import Path

import yaml


def test_production_compose_contains_required_internal_services():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    for service in ("backend", "postgres", "redis", "minio", "celery-worker", "celery-worker-low-priority"):
        assert service in services
    assert "volumes" not in services["backend"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert services["backend"]["healthcheck"]["test"][-1].endswith("/api/v1/system/health")


def test_production_workers_consume_backend_routed_queues():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    worker_command = compose["services"]["celery-worker"]["command"]

    for queue in ("tool_tasks", "maintenance", "monitoring"):
        assert queue in worker_command
