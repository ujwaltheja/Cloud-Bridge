"""Metadata Comparison table

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_comparisons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_retrieval_id", sa.UUID(), nullable=True),
        sa.Column("target_retrieval_id", sa.UUID(), nullable=True),
        sa.Column("source_org_id", sa.UUID(), nullable=False),
        sa.Column("target_org_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("diff_summary", sa.JSON(), nullable=True),
        sa.Column("diff_artifact_key", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("metadata_comparisons")
