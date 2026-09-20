"""GPU lease 持久化与并发占用测试。"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.models.gpu as _gpu_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models.gpu import GPUAllocation, GPUAllocationStatus
from app.models.tasks import Task, TaskStatus
from app.gpu.allocator import GPUAllocator
from app.common.time import utcnow


class _SingleGpuDetector:
    def is_available(self):
        return True

    def get_node_info(self):
        return type(
            "NodeInfo",
            (),
            {
                "hostname": "gpu-host",
                "gpu_count": 1,
                "gpus": [
                    type(
                        "GpuInfo",
                        (),
                        {
                            "gpu_index": 0,
                            "gpu_name": "GPU 0",
                            "total_memory_mb": 24_000,
                            "free_memory_mb": 16_000,
                        },
                    )()
                ],
            },
        )()

    def get_gpu_stats(self, gpu_index: int):
        return type("GpuStats", (), {"utilization_percent": 0})()

    def get_all_gpu_stats(self):
        return [
            type(
                "GpuStats",
                (),
                {
                    "gpu_index": 0,
                    "utilization_percent": 0,
                    "memory_used_mb": 0,
                    "memory_free_mb": 16_000,
                    "memory_total_mb": 24_000,
                    "temperature_celsius": 35,
                },
            )()
        ]


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield session_factory
    await engine.dispose()


async def _create_task(db: AsyncSession, task_id: str) -> Task:
    task = Task(
        id=task_id,
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        status=TaskStatus.RUNNING.value,
        extra_data={"execution_attempt_id": f"attempt-{task_id}"},
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.asyncio
async def test_gpu_lease_blocks_second_active_claim(db_session_factory):
    async with db_session_factory() as db:
        first_task = await _create_task(db, "task-1")
        second_task = await _create_task(db, "task-2")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())

        first = await allocator._create_allocation(
            task_id=first_task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-1",
        )
        await db.commit()

        second = await allocator._create_allocation(
            task_id=second_task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-2",
        )

        assert first.success is True
        assert second.success is False
        assert "占用" in second.message


@pytest.mark.asyncio
async def test_release_marks_lease_released_and_clears_task(db_session_factory):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-release")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-release",
        )
        await db.commit()

        assert await allocator.release(task.id, allocation.allocation_id) is True
        stored_lease = (
            await db.execute(select(GPUAllocation).where(GPUAllocation.id == allocation.allocation_id))
        ).scalar_one()
        stored_task = await db.get(Task, task.id)

        assert stored_lease.status == GPUAllocationStatus.RELEASED.value
        assert stored_lease.released_at is not None
        assert stored_task.gpu_node_id is None
        assert stored_task.gpu_index is None
        assert stored_task.gpu_memory_allocated_mb is None


@pytest.mark.asyncio
async def test_allocation_stats_include_active_leases(db_session_factory):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-stats")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-stats",
        )
        await db.commit()

        stats = await allocator.get_allocation_stats()

        assert stats["allocations"] == [
            {
                "allocation_id": allocation.allocation_id,
                "task_id": task.id,
                "execution_attempt_id": "attempt-task-stats",
                "gpu_node_id": "local",
                "gpu_index": 0,
                "memory_allocated_mb": 4096,
                "status": GPUAllocationStatus.ACTIVE.value,
            }
        ]


@pytest.mark.asyncio
async def test_heartbeat_updates_active_lease(db_session_factory, monkeypatch):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-heartbeat")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-heartbeat",
        )
        await db.commit()
        lease = await db.get(GPUAllocation, allocation.allocation_id)
        heartbeat_at = lease.heartbeat_at + timedelta(seconds=30)
        monkeypatch.setattr("app.gpu.allocator.utcnow", lambda: heartbeat_at)

        assert await allocator.heartbeat(task.id, allocation.allocation_id) is True
        await db.commit()
        await db.refresh(lease)

        assert lease.heartbeat_at == heartbeat_at


@pytest.mark.asyncio
async def test_reclaim_stale_lease_releases_task_device(db_session_factory, monkeypatch):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-stale")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-task-stale",
        )
        await db.commit()
        lease = await db.get(GPUAllocation, allocation.allocation_id)
        now = utcnow()
        lease.heartbeat_at = now - timedelta(minutes=10)
        await db.commit()
        monkeypatch.setattr("app.gpu.allocator.utcnow", lambda: now)

        assert await allocator.reclaim_stale_allocations(timeout_seconds=300) == 1
        await db.commit()
        await db.refresh(lease)
        await db.refresh(task)

        assert lease.status == GPUAllocationStatus.RELEASED.value
        assert lease.released_at == now
        assert task.gpu_node_id is None
        assert task.gpu_index is None
        assert task.gpu_memory_allocated_mb is None


@pytest.mark.asyncio
async def test_reclaim_stale_lease_does_not_clear_newer_task_device(
    db_session_factory,
    monkeypatch,
):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-retry-lease")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        old_allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-old",
        )
        await db.commit()

        new_allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=1,
            memory_mb=4096,
            attempt_id="attempt-new",
        )
        await db.commit()
        old_lease = await db.get(GPUAllocation, old_allocation.allocation_id)
        now = utcnow()
        old_lease.heartbeat_at = now - timedelta(minutes=10)
        await db.commit()
        monkeypatch.setattr("app.gpu.allocator.utcnow", lambda: now)

        assert await allocator.reclaim_stale_allocations(timeout_seconds=300) == 1
        await db.commit()
        await db.refresh(task)

        assert task.gpu_node_id == "local"
        assert task.gpu_index == 1
        assert task.gpu_memory_allocated_mb == 4096
        assert new_allocation.allocation_id != old_allocation.allocation_id


@pytest.mark.asyncio
async def test_release_old_lease_does_not_clear_newer_task_device(db_session_factory):
    async with db_session_factory() as db:
        task = await _create_task(db, "task-release-retry")
        allocator = GPUAllocator(db=db, detector=_SingleGpuDetector())
        old_allocation = await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=0,
            memory_mb=4096,
            attempt_id="attempt-old",
        )
        await db.commit()
        await allocator._create_allocation(
            task_id=task.id,
            node_id="local",
            gpu_index=1,
            memory_mb=4096,
            attempt_id="attempt-new",
        )
        await db.commit()

        assert await allocator.release(task.id, old_allocation.allocation_id) is True
        await db.commit()
        await db.refresh(task)

        assert task.gpu_node_id == "local"
        assert task.gpu_index == 1
        assert task.gpu_memory_allocated_mb == 4096
