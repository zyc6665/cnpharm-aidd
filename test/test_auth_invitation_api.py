from app.api.v1.auth import router


def test_invitation_endpoint_is_not_exposed():
    assert all(route.path != '/invitation/validate' for route in router.routes)
