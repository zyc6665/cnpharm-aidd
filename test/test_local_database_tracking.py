import subprocess
from pathlib import Path


def test_local_application_database_is_ignored_and_not_tracked():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    tracked_files = subprocess.run(
        ["git", "ls-files", "backend/app.db"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert "backend/app.db" in gitignore
    assert tracked_files == []


def test_backend_secrets_and_database_globs_are_ignored_and_not_tracked():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    tracked_files = subprocess.run(
        ["git", "ls-files", "backend/.env", "backend/app.db"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    for pattern in ("backend/.env", "backend/*.db", "backend/*.db-*"):
        assert pattern in gitignore
    assert tracked_files == []
