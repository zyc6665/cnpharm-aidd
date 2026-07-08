from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP_ROOT = PROJECT_ROOT / "backend" / "app"


def test_backend_app_does_not_use_datetime_utcnow_directly() -> None:
    offenders: list[str] = []

    for path in sorted(BACKEND_APP_ROOT.rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        if "datetime.utcnow(" not in content:
            continue
        offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], (
        "backend/app 中不应再直接使用 datetime.utcnow()，"
        "请统一改为共享的 utcnow() helper: "
        + ", ".join(offenders)
    )


def test_backend_app_does_not_define_duplicate_utc_helpers() -> None:
    offenders: list[str] = []

    for path in sorted(BACKEND_APP_ROOT.rglob("*.py")):
        if path == BACKEND_APP_ROOT / "common" / "time.py":
            continue
        content = path.read_text(encoding="utf-8")
        if "def utcnow(" in content or "datetime.now(UTC)" in content:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], (
        "backend/app 中不应重复定义 UTC 时间 helper，"
        "请复用 app.common.time: "
        + ", ".join(offenders)
    )


def test_backend_app_does_not_use_datetime_fromtimestamp_directly() -> None:
    offenders: list[str] = []

    for path in sorted(BACKEND_APP_ROOT.rglob("*.py")):
        if path == BACKEND_APP_ROOT / "common" / "time.py":
            continue
        content = path.read_text(encoding="utf-8")
        if "datetime.fromtimestamp(" in content:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], (
        "backend/app 中不应直接使用 datetime.fromtimestamp()，"
        "请复用 app.common.time.utcfromtimestamp(): "
        + ", ".join(offenders)
    )


def test_backend_app_does_not_build_z_suffix_timestamps_manually() -> None:
    offenders: list[str] = []

    for path in sorted(BACKEND_APP_ROOT.rglob("*.py")):
        if path == BACKEND_APP_ROOT / "common" / "time.py":
            continue
        content = path.read_text(encoding="utf-8")
        if 'isoformat() + "Z"' in content or "isoformat() + 'Z'" in content:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], (
        "backend/app 中不应手写 isoformat() + 'Z'，"
        "请复用统一时间序列化 helper: "
        + ", ".join(offenders)
    )
