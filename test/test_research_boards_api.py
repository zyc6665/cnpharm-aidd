import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.research_boards import (
    create_research_board,
    create_workflow_draft,
    get_research_board,
    list_research_boards,
    update_research_board,
)
from app.database.base import Base
from app.models import artifacts as _artifacts, users as _users, workflows as _workflows  # noqa: F401
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.users import User
from app.models.files import File
from app.models.tools import Tool, ToolVersion
from app.models.workflows import ResearchBoard
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
async def test_board_workflow_draft_preserves_artifact_nodes_as_workflow_inputs(db_session):
    owner = make_user('owner@example.com')
    protein_tool = Tool(
        owner=owner,
        name='Pocket tool',
        slug='pocket-tool',
        status='published',
        is_public=True,
    )
    db_session.add_all([owner, protein_tool])
    await db_session.flush()
    tool_version = ToolVersion(
        tool_id=protein_tool.id,
        version='1.0.0',
        config={
            'type': 'python_script',
            'artifacts': {
                'inputs': [
                    {'name': 'protein', 'type': 'protein_structure@1', 'required': True}
                ],
                'outputs': [
                    {'name': 'pocket', 'type': 'binding_pocket@1', 'required': True}
                ],
            },
        },
    )
    db_session.add(tool_version)
    await db_session.flush()
    protein_tool.current_version_id = tool_version.id

    artifact = Artifact(
        project_id='project-1',
        created_by=owner.id,
        artifact_type='protein_structure',
        semantic_type='protein_structure@1',
        standard_type='protein_structure',
        standard_version=1,
        name='1ABC',
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename='1ABC.pdb',
        content_type='chemical/x-pdb',
        size_bytes=24,
        sha256='a' * 64,
        storage_key='standard/1ABC.pdb',
        status='available',
    )
    file_record = FileModel(
        project_id='project-1',
        owner_id=owner.id,
        filename='1ABC.pdb',
        content_type='chemical/x-pdb',
        size_bytes=24,
        sha256='a' * 64,
        storage_path='standard/1ABC.pdb',
    )
    db_session.add_all([version, file_record])
    await db_session.flush()
    db_session.add(
        ArtifactVersionFile(
            artifact_version_id=version.id,
            role='structure_file',
            file_id=file_record.id,
            is_primary=True,
            sort_order=0,
        )
    )
    artifact.latest_version_id = version.id
    await db_session.commit()

    board = await create_research_board(
        ResearchBoardCreate(
            name='External protein workflow',
            content={
                'nodes': [
                    {
                        'id': 'artifact-protein',
                        'type': 'artifact',
                        'position': {'x': 0, 'y': 0},
                        'artifact_id': artifact.id,
                    },
                    {
                        'id': 'tool-pocket',
                        'type': 'tool',
                        'position': {'x': 320, 'y': 0},
                        'tool_id': protein_tool.id,
                    },
                ],
                'edges': [],
                'viewport': {'x': 0, 'y': 0, 'zoom': 1},
            },
        ),
        owner,
        db_session,
    )

    draft = await create_workflow_draft(board['data']['id'], owner, db_session)

    definition = draft['data']['definition']
    nodes_by_id = {node['id']: node for node in definition['nodes']}
    assert nodes_by_id['artifact-protein']['kind'] == 'input'
    assert nodes_by_id['artifact-protein']['semantic_type'] == 'protein_structure@1'
    assert nodes_by_id['tool-pocket']['artifact_inputs'] == {
        'protein': 'workflow_input:protein_structure@1'
    }
    assert definition['edges'] == [
        {
            'id': 'artifact-protein->tool-pocket:protein_structure@1',
            'source': 'artifact-protein',
            'target': 'tool-pocket',
            'source_output': 'protein_structure@1',
            'target_input': 'protein',
        }
    ]
    assert definition['artifact_bindings_by_node'] == {
        'tool-pocket': {'protein': version.id}
    }
    assert draft['data']['input_files'] == {'protein_structure@1': file_record.id}


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


@pytest.mark.asyncio
async def test_board_reads_tolerate_legacy_content_shapes(db_session):
    owner = make_user('owner@example.com')
    tool = Tool(owner=owner, name='Pocket tool', slug='pocket-tool', status='published', is_public=True)
    db_session.add_all([owner, tool])
    await db_session.flush()
    board = ResearchBoard(
        owner_id=owner.id,
        name='Legacy board',
        content=[
            {'id': 'tool-1', 'type': 'tool', 'position': {'x': 0, 'y': 0}, 'tool_id': tool.id},
            'broken-node',
        ],
    )
    db_session.add(board)
    await db_session.commit()
    await db_session.refresh(board)

    listed = await list_research_boards(1, 20, None, owner, db_session)
    loaded = await get_research_board(board.id, owner, db_session)
    draft = await create_workflow_draft(board.id, owner, db_session)

    assert listed['data']['items'][0]['node_count'] == 1
    assert loaded['data']['content']['nodes'][0]['id'] == 'tool-1'
    assert draft['data']['definition']['selected_tool_by_node'] == {'tool-1': 'pocket-tool'}
