def test_builtin_executor_has_a_dedicated_module_and_legacy_import():
    from app.tasks.executor import BuiltinExecutor as LegacyBuiltinExecutor
    from app.tasks.executors.builtin import BuiltinExecutor

    assert LegacyBuiltinExecutor is BuiltinExecutor
