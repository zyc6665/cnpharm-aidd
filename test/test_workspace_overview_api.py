import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.workspace import get_workspace_overview
from app.database.base import Base
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User


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
async def test_workspace_overview_returns_recent_typed_artifacts_for_member_projects(db_session):
    owner = User(email='owner@example.com', password_hash='test', status='active')
    other = User(email='other@example.com', password_hash='test', status='active')
    organization = Organization(name='Workspace Lab', slug='workspace-lab')
    db_session.add_all([owner, other, organization])
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name='EGFR Project',
        status='active',
    )
    foreign_project = Project(
        organization_id=organization.id,
        created_by=other.id,
        name='Foreign Project',
        status='active',
    )
    db_session.add_all([project, foreign_project])
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=owner.id, role='owner'))
    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type='binding_pocket',
        semantic_type='binding_pocket',
        standard_type='binding_pocket',
        standard_version=1,
        name='egfr-pocket',
    )
    expired = Artifact(
        project_id=foreign_project.id,
        created_by=other.id,
        artifact_type='binding_pocket',
        semantic_type='binding_pocket',
        standard_type='binding_pocket',
        standard_version=1,
        name='foreign-pocket',
    )
    db_session.add_all([artifact, expired])
    await db_session.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename='egfr-pocket.pdb',
        content_type='chemical/x-pdb',
        size_bytes=2048,
        sha256='a' * 64,
        storage_key='artifacts/egfr-pocket.pdb',
        status='available',
    )
    foreign_version = ArtifactVersion(
        artifact_id=expired.id,
        created_by=other.id,
        version=1,
        filename='foreign-pocket.pdb',
        content_type='chemical/x-pdb',
        size_bytes=1024,
        sha256='b' * 64,
        storage_key='artifacts/foreign-pocket.pdb',
        status='available',
    )
    db_session.add_all([version, foreign_version])
    await db_session.flush()
    artifact.latest_version_id = version.id
    expired.latest_version_id = foreign_version.id
    await db_session.commit()

    response = await get_workspace_overview(owner, db_session)

    artifacts = response['data']['artifacts']
    assert [item['name'] for item in artifacts] == ['egfr-pocket']
    assert artifacts[0]['artifact_type'] == 'binding_pocket'
    assert artifacts[0]['standard_type'] == 'binding_pocket'
    assert artifacts[0]['standard_version'] == 1
    assert artifacts[0]['latest_version']['id'] == version.id
    assert artifacts[0]['latest_version']['filename'] == 'egfr-pocket.pdb'
