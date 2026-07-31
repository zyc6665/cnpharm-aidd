import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.research_boards import (
    create_research_board,
    create_workflow_draft,
    get_research_board,
    update_research_board,
)
from app.database.base import Base
from app.models import users as _users, workflows as _workflows  # noqa: F401
from app.models.users import User
from app.models.files import File
from app.models.tools import Tool
from app.schemas.research_boards import ResearchBoardCreate
from app.schemas.research_boards import ResearchBoardUpdate
from pydantic import ValidationError


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


def make_user(email: str, role: str = 'user') -> User:
    return User(email=email, password_hash='test', display_name=email.split('@')[0], role=role)


@pytest.mark.asyncio
async def test_owner_can_create_board_and_convert_tool_node_to_workflow_draft(db_session):
    owner = make_user('owner@example.com')
    tool = Tool(owner=owner, name='Pocket tool', slug='pocket-tool', status='published', is_public=True)
    db_session.add_all([owner, tool])
    await db_session.commit()

    board = await create_research_board(
        ResearchBoardCreate(
            name='Target research',
            content={
                'nodes': [
                    {'id': 'note-1', 'type': 'note', 'position': {'x': 0, 'y': 0}, 'content': 'Hypothesis'},
                    {'id': 'tool-1', 'type': 'tool', 'position': {'x': 320, 'y': 0}, 'tool_id': tool.id},
                ],
                'edges': [],
                'viewport': {'x': 0, 'y': 0, 'zoom': 1},
            },
        ),
        owner,
        db_session,
    )

    board_id = board['data']['id']
    draft = await create_workflow_draft(board_id, owner, db_session)

    assert draft['data']['name'] == 'Target research workflow'
    assert draft['data']['nodes'][0]['tool_id'] == tool.id
    assert draft['data']['definition']['selected_tool_by_node'] == {'tool-1': 'pocket-tool'}


@pytest.mark.asyncio
async def test_board_is_private_except_for_admin_read_access(db_session):
    owner = make_user('owner@example.com')
    other = make_user('other@example.com')
    admin = make_user('admin@example.com', role='admin')
    db_session.add_all([owner, other, admin])
    await db_session.commit()

    board = await create_research_board(ResearchBoardCreate(name='Private board'), owner, db_session)
    board_id = board['data']['id']

    with pytest.raises(HTTPException) as exc:
        await get_research_board(board_id, other, db_session)
    assert exc.value.status_code == 404

    loaded = await get_research_board(board_id, admin, db_session)
    assert loaded['data']['id'] == board_id


def test_board_schema_rejects_duplicate_nodes_and_unbound_references():
    with pytest.raises(ValidationError):
        ResearchBoardCreate(
            name='Invalid board',
            content={
                'nodes': [
                    {'id': 'same', 'type': 'note', 'position': {'x': 0, 'y': 0}, 'content': 'a'},
                    {'id': 'same', 'type': 'note', 'position': {'x': 1, 'y': 1}, 'content': 'b'},
                ],
                'edges': [],
                'viewport': {'x': 0, 'y': 0, 'zoom': 1},
            },
        )

    with pytest.raises(ValidationError):
        ResearchBoardCreate(
            name='Invalid tool',
            content={
                'nodes': [{'id': 'tool', 'type': 'tool', 'position': {'x': 0, 'y': 0}}],
                'edges': [],
                'viewport': {'x': 0, 'y': 0, 'zoom': 1},
            },
        )


@pytest.mark.asyncio
async def test_board_update_uses_optimistic_version(db_session):
    owner = make_user('owner@example.com')
    db_session.add(owner)
    await db_session.commit()
    board = await create_research_board(ResearchBoardCreate(name='Versioned'), owner, db_session)

    updated = await update_research_board(
        board['data']['id'],
        ResearchBoardUpdate(name='Updated', version=1),
        owner,
        db_session,
    )
    assert updated['data']['version'] == 2

    with pytest.raises(HTTPException) as exc:
        await update_research_board(
            board['data']['id'],
            ResearchBoardUpdate(name='Stale', version=1),
            owner,
            db_session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_board_rejects_file_owned_by_another_user(db_session):
    owner = make_user('owner@example.com')
    other = make_user('other@example.com')
    file = File(
        owner=other,
        filename='private.pdb',
        size_bytes=12,
        sha256='a' * 64,
        storage_path='/tmp/private.pdb',
    )
    db_session.add_all([owner, other, file])
    await db_session.commit()

    payload = ResearchBoardCreate(
        name='Invalid reference',
        content={
            'nodes': [{'id': 'file-1', 'type': 'file', 'position': {'x': 0, 'y': 0}, 'file_id': file.id}],
            'edges': [],
            'viewport': {'x': 0, 'y': 0, 'zoom': 1},
        },
    )
    with pytest.raises(HTTPException) as exc:
        await create_research_board(payload, owner, db_session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_board_read_is_audited(db_session, monkeypatch):
    owner = make_user('owner@example.com')
    admin = make_user('admin@example.com', role='admin')
    db_session.add_all([owner, admin])
    await db_session.commit()
    board = await create_research_board(ResearchBoardCreate(name='Audited'), owner, db_session)
    events = []
    monkeypatch.setattr('app.api.v1.research_boards.audit_board_read', lambda **data: events.append(data))

    await get_research_board(board['data']['id'], admin, db_session)

    assert events == [{'admin_id': admin.id, 'board_id': board['data']['id'], 'owner_id': owner.id}]
