import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.workspace import get_workspace_overview
from app.database.base import Base
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.models.workflows import ResearchBoard


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_counts_all_attention_tasks_and_isolates_owner(db_session):
    owner = User(email='owner@example.com', password_hash='test', status='active')
    other = User(email='other@example.com', password_hash='test', status='active')
    tool = Tool(owner=owner, name='Docking', slug='docking', status='published')
    version = ToolVersion(tool=tool, version='1.0', config={})
    db_session.add_all([owner, other, tool, version])
    await db_session.flush()
    db_session.add_all([
        Task(user_id=owner.id, tool_id=tool.id, tool_version_id=version.id, name=f'Owner {index}', status=TaskStatus.PENDING.value)
        for index in range(13)
    ])
    db_session.add(Task(user_id=other.id, tool_id=tool.id, tool_version_id=version.id, name='Other task', status=TaskStatus.FAILURE.value))
    await db_session.commit()

    response = await get_workspace_overview(owner, db_session)

    assert response['data']['attention_task_count'] == 13
    assert response['data']['task_status_counts']['pending'] == 13
    assert len(response['data']['tasks']) == 12
    assert all(task['name'].startswith('Owner') for task in response['data']['tasks'])
    assert all(task['tool_name'] == 'Docking' for task in response['data']['tasks'])


@pytest.mark.asyncio
async def test_workspace_overview_tolerates_legacy_board_content_shapes(db_session):
    owner = User(email='owner@example.com', password_hash='test', status='active')
    db_session.add(owner)
    await db_session.flush()
    db_session.add_all([
        ResearchBoard(
            owner_id=owner.id,
            name='Legacy list board',
            content=[{'id': 'note-1', 'type': 'note'}],
        ),
        ResearchBoard(
            owner_id=owner.id,
            name='Legacy scalar board',
            content='not-json-object',
        ),
    ])
    await db_session.commit()

    response = await get_workspace_overview(owner, db_session)

    boards = {board['name']: board for board in response['data']['boards']}
    assert boards['Legacy list board']['node_count'] == 1
    assert boards['Legacy scalar board']['node_count'] == 0
