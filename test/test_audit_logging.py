from app.logging.audit import AuditAction, AuditEvent, AuditLogger, AuditResult


def test_db_logging_without_writer_warns_once(caplog, tmp_path):
    """启用数据库审计但未配置写入器时，应显式告警且不重复刷屏。"""
    audit_logger = AuditLogger(
        log_dir=str(tmp_path),
        enable_file_logging=False,
        enable_db_logging=True,
    )

    caplog.set_level("WARNING", logger="app.logging.audit")

    audit_logger.log(AuditEvent(action=AuditAction.LOGIN))
    audit_logger.log(AuditEvent(action=AuditAction.LOGOUT))

    warnings = [
        record
        for record in caplog.records
        if "no db_writer is configured" in record.message
    ]
    assert len(warnings) == 1


def test_db_logging_uses_configured_writer(tmp_path):
    """配置数据库写入器后，审计事件应交给写入器处理。"""
    written_events = []
    audit_logger = AuditLogger(
        log_dir=str(tmp_path),
        enable_file_logging=False,
        enable_db_logging=True,
        db_writer=written_events.append,
        sanitize=False,
    )
    event = AuditEvent(action=AuditAction.PASSWORD_CHANGE, result=AuditResult.SUCCESS)

    audit_logger.log(event)

    assert written_events == [event]
