from pathlib import Path


def test_celery_start_script_matches_compose_flower_endpoint():
    script = Path("scripts/start-celery.sh").read_text(encoding="utf-8")
    compose = Path("deploy/compose/docker-compose.dev.yml").read_text(encoding="utf-8")
    quickref = Path("docs/archive-upstream/guides/CELERY_QUICKREF.md").read_text(encoding="utf-8")
    deployment = Path("docs/archive-upstream/guides/CELERY_DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "http://localhost:9555" in script
    assert '"9555:9555"' in compose
    assert "docs/archive-upstream/guides/CELERY_DEPLOYMENT.md" in script
    assert "http://localhost:5555" not in quickref
    assert "http://localhost:5555" not in deployment
    assert "0.0.0.0:5555->5555/tcp" not in deployment


def test_active_celery_deployment_files_use_the_real_app_module():
    active_files = (
        "scripts/start-celery.sh",
        "deploy/compose/docker-compose.dev.yml",
        "docs/archive-upstream/guides/CELERY_DEPLOYMENT.md",
        "docs/archive-upstream/guides/CELERY_QUICKREF.md",
    )

    for file_name in active_files:
        source = Path(file_name).read_text(encoding="utf-8")
        assert "app.celery_app.celery_app" not in source
        assert "backend/app/celery_app" not in source
        assert "from app.celery_app" not in source
        assert "app.worker.celery_app" in source
