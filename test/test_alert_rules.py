import pytest

from app.monitoring import alert_rules


class QueueLengthCache:
    def __init__(self, value):
        self.value = value
        self.key = None

    async def get(self, key: str):
        self.key = key
        return self.value


@pytest.mark.asyncio
async def test_celery_queue_length_uses_cache_backend_factory(monkeypatch):
    """Celery 队列长度检查应使用真实缓存工厂入口。"""
    cache = QueueLengthCache("7")
    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: cache,
    )

    length = await alert_rules.check_celery_queue_length()

    assert length == 7
    assert cache.key == "celery:queue:default:length"


@pytest.mark.asyncio
async def test_celery_queue_length_falls_back_to_zero_on_cache_error(monkeypatch):
    """缓存读取失败时队列长度检查应安全降级为 0。"""
    class FailingCache:
        async def get(self, key: str):
            raise RuntimeError("cache unavailable")

    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: FailingCache(),
    )

    assert await alert_rules.check_celery_queue_length() == 0
