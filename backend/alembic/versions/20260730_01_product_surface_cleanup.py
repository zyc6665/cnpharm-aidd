"""Add research boards and remove retired monetization data.

Revision ID: 20260730_01
Revises: 20260729_01
"""

import sqlalchemy as sa
from alembic import op

revision = '20260730_01'
down_revision = '20260729_01'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' in inspector.get_table_names():
        bind.execute(sa.text("UPDATE users SET role = 'user' WHERE role = 'vip'"))
    if 'user_statistics' in inspector.get_table_names():
        columns = {column['name'] for column in inspector.get_columns('user_statistics')}
        if 'total_credits_used' in columns:
            with op.batch_alter_table('user_statistics') as batch:
                batch.drop_column('total_credits_used')
    if 'research_boards' not in sa.inspect(bind).get_table_names():
        op.create_table(
            'research_boards',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('name', sa.String(160), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('content', sa.JSON(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )
        op.create_index('ix_research_boards_owner_id', 'research_boards', ['owner_id'])
        op.create_index('ix_research_boards_name', 'research_boards', ['name'])
    elif 'version' not in {column['name'] for column in sa.inspect(bind).get_columns('research_boards')}:
        with op.batch_alter_table('research_boards') as batch:
            batch.add_column(sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade():
    if 'research_boards' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('research_boards')
    with op.batch_alter_table('user_statistics') as batch:
        batch.add_column(sa.Column('total_credits_used', sa.Float(), nullable=False, server_default='0'))
