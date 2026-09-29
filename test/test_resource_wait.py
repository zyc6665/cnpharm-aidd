"""资源等待原因分类测试。"""

from app.tasks.resource_wait import describe_resource_wait, resource_wait_metadata


def test_describe_user_cpu_quota_wait():
    descriptor = describe_resource_wait("user_cpu_quota_exhausted")

    assert descriptor == type(descriptor)(
        reason="user_cpu_quota_exhausted",
        category="quota",
        scope="user",
        dimension="cpu",
    )


def test_describe_project_memory_quota_wait_normalizes_dimension():
    descriptor = describe_resource_wait("project_memory_gb_quota_exhausted")

    assert descriptor.category == "quota"
    assert descriptor.scope == "project"
    assert descriptor.dimension == "memory"


def test_resource_wait_metadata_preserves_legacy_reason():
    metadata = resource_wait_metadata(
        "user_parallelism_quota_exhausted",
        legacy_reason="worker_capability_unavailable",
    )

    assert metadata == {
        "resource_wait_reason": "worker_capability_unavailable",
        "resource_wait_code": "user_parallelism_quota_exhausted",
        "resource_wait_category": "quota",
        "resource_wait_scope": "user",
        "resource_wait_dimension": "parallelism",
    }
