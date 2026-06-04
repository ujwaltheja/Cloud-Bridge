"""Salesforce Org Management tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salesforce_orgs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("org_type", sa.String(length=50), nullable=False),
        sa.Column("auth_method", sa.String(length=50), nullable=False),
        sa.Column("org_id", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("instance_url", sa.String(length=255), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("encrypted_access_token", sa.String(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.String(), nullable=True),
        sa.Column("encrypted_private_key", sa.String(), nullable=True),
        sa.Column("last_connection_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_status", sa.String(length=50), nullable=True),
        sa.Column("last_connection_error", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_salesforce_orgs_username"), "salesforce_orgs", ["username"])
    op.create_index(op.f("ix_salesforce_orgs_org_id"), "salesforce_orgs", ["org_id"])


def downgrade() -> None:
    op.drop_table("salesforce_orgs")
