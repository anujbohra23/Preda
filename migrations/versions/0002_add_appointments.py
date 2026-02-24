"""Add appointments and appointment_actions tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('doctor_name', sa.Text(), nullable=True),
        sa.Column('appointment_date', sa.Text(), nullable=True),
        sa.Column('capture_method', sa.Text(), nullable=True),
        sa.Column('audio_path', sa.Text(), nullable=True),
        sa.Column('raw_transcript', sa.Text(), nullable=True),
        sa.Column('summary_json', sa.Text(), nullable=True),
        sa.Column('followup_date', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointments_session_id', 'appointments', ['session_id'])
    op.create_index('ix_appointments_user_id', 'appointments', ['user_id'])

    op.create_table('appointment_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Text(), nullable=True),
        sa.Column('is_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('appointment_actions')
    op.drop_index('ix_appointments_user_id', 'appointments')
    op.drop_index('ix_appointments_session_id', 'appointments')
    op.drop_table('appointments')