"""Initial schema all tables

Revision ID: 0001
Revises:
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('pw_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('deleted_at', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table('sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('safety_flagged', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])

    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('event_detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('disease_catalog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('disease_name', sa.Text(), nullable=False),
        sa.Column('icd_code', sa.Text(), nullable=True),
        sa.Column('short_desc', sa.Text(), nullable=True),
        sa.Column('embedding_blob', sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('intake_fields',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.Text(), nullable=False),
        sa.Column('field_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.Text(), nullable=True),
        sa.Column('stored_path', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('extracted_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('upload_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=True),
        sa.Column('edited_text', sa.Text(), nullable=True),
        sa.Column('is_confirmed', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.ForeignKeyConstraint(['upload_id'], ['uploads.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('disease_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('disease_id', sa.Integer(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('explanation_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['disease_id'], ['disease_catalog.id']),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('safety_triggered', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('report_type', sa.Text(), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=True),
        sa.Column('pdf_path', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('rag_retrievals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_message_id', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('citation_label', sa.Text(), nullable=True),
        sa.Column('source_doc_name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['chat_message_id'], ['chat_messages.id']),
        sa.ForeignKeyConstraint(['chunk_id'], ['extracted_chunks.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('rag_retrievals')
    op.drop_table('reports')
    op.drop_table('chat_messages')
    op.drop_table('disease_results')
    op.drop_table('extracted_chunks')
    op.drop_table('uploads')
    op.drop_table('intake_fields')
    op.drop_table('disease_catalog')
    op.drop_table('audit_logs')
    op.drop_index('ix_sessions_user_id', 'sessions')
    op.drop_table('sessions')
    op.drop_index('ix_users_email', 'users')
    op.drop_table('users')
