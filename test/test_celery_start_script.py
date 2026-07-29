from pathlib import Path


def test_celery_start_script_matches_compose_flower_endpoint():
    script = Path("start-celery.sh").read_text(encoding="utf-8")
    compose = Path("docker-compose.celery.yml").read_text(encoding="utf-8")

    assert "http://localhost:9555" in script
    assert '"9555:9555"' in compose
    assert "document/CELERY_DEPLOYMENT.md" in script
