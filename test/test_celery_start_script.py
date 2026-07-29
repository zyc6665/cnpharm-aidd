from pathlib import Path


def test_celery_start_script_matches_compose_flower_endpoint():
    script = Path("start-celery.sh").read_text(encoding="utf-8")
    compose = Path("docker-compose.celery.yml").read_text(encoding="utf-8")

    assert "http://localhost:9555" in script
    assert '"9555:9555"' in compose
    assert "document/CELERY_DEPLOYMENT.md" in script


def test_active_celery_deployment_files_use_the_real_app_module():
    active_files = (
        "start-celery.sh",
        "docker-compose.celery.yml",
        "document/CELERY_DEPLOYMENT.md",
        "document/CELERY_QUICKREF.md",
    )

    for file_name in active_files:
        source = Path(file_name).read_text(encoding="utf-8")
        assert "app.celery_app.celery_app" not in source
        assert "app.worker.celery_app" in source
