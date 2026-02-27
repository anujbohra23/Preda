"""Add language preference to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(
            sa.Column('preferred_language', sa.Text(),
                      nullable=False, server_default='en')
        )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('preferred_language')
