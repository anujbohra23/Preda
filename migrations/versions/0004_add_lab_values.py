"""0004 add lab_values table

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lab_values",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("sessions.id"),
                  nullable=False, index=True),
        sa.Column("upload_id", sa.Integer, sa.ForeignKey("uploads.id"),
                  nullable=True),
        # Normalized test name e.g. "HbA1c", "Creatinine", "LDL Cholesterol"
        sa.Column("test_name", sa.Text, nullable=False, index=True),
        # Numeric value (None if non-numeric)
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("unit", sa.Text, nullable=True),
        # Original string from report e.g. "5.8 %"
        sa.Column("raw_value", sa.Text, nullable=True),
        # e.g. "4.0-5.6" or "< 200"
        sa.Column("reference_range", sa.Text, nullable=True),
        # "normal", "high", "low", "unknown"
        sa.Column("status", sa.Text, nullable=True),
        # Date from the report itself (not upload date)
        sa.Column("report_date", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_lab_values_user_test",
        "lab_values",
        ["user_id", "test_name"],
    )


def downgrade():
    op.drop_index("ix_lab_values_user_test", "lab_values")
    op.drop_table("lab_values")