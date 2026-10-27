"""CI 门禁必须真的存在，否则规范只是文档里的字。

这些测试锁的是「流水线实际跑了什么」——不是文档写了什么。
改动工作流时如果删掉某个门禁，这里会立刻失败。
"""

from pathlib import Path

import yaml


def _workflow() -> dict:
    return yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))


def _commands(job: dict) -> list[str]:
    return [step.get("run", "") for step in job["steps"]]


def test_backend_development_dependencies_pin_flake8():
    requirements = Path("backend/requirements-dev.txt").read_text(encoding="utf-8").splitlines()

    assert "flake8==7.1.1" in requirements


def test_backend_lint_job_checks_unused_imports_and_syntax():
    """F401 曾是 develop 上的常红项，必须由独立作业把关。"""
    job = _workflow()["jobs"]["backend-lint"]
    commands = _commands(job)

    assert any("pip install -r backend/requirements-dev.txt" in command for command in commands)
    assert any("python -m flake8 backend/app --select F401" in command for command in commands)
    assert any("python -m flake8 backend/app --select F821,E9" in command for command in commands)


def test_backend_test_job_gates_on_lint():
    """测试作业必须等规范检查通过，避免 lint 问题埋进测试日志。"""
    workflow = _workflow()
    job = workflow["jobs"]["backend-test"]

    assert job["needs"] == "backend-lint"
    assert any("python -m pytest test/" in command for command in _commands(job))


def test_every_ci_job_has_a_chinese_display_name():
    """分支保护的 contexts 用的是 job.name，匿名作业无法被保护规则引用。"""
    for job_key, job in _workflow()["jobs"].items():
        assert job.get("name"), f"作业 {job_key} 缺少 name，无法加入分支保护 contexts"
        assert job["name"] != job_key, f"作业 {job_key} 的 name 应与 job key 区分，便于人工阅读"


def test_migrations_are_verified_on_postgres():
    """迁移链必须有一个真 PostgreSQL 的作业。

    SQLite 不校验外键目标是否存在、也不做跨表依赖检查，迁移链里的悬空外键与
    删除顺序问题在 SQLite 上全是绿灯。交付环境按 docs/13 用 PostgreSQL，所以
    必须有真 PG 双向（upgrade + downgrade）验证。此前 33 次迁移验证全在 SQLite
    上，一次上 PG 就同时暴露了三个缺陷（基线漏建表、删除顺序反了、收尾漏删）。
    """
    job = _workflow()["jobs"]["migrations-postgres"]
    commands = _commands(job)

    assert job["name"] == "迁移链（PostgreSQL）"
    services = job.get("services") or {}
    assert "postgres" in services, "迁移作业必须起一个真的 PostgreSQL 服务容器"
    assert str(services["postgres"]["image"]).startswith("postgres:")
    assert any("alembic upgrade head" in command for command in commands)
    assert any("alembic downgrade base" in command for command in commands)
