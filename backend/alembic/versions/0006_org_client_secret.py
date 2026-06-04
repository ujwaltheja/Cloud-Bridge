"""Add encrypted_client_secret to salesforce_orgs

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "salesforce_orgs",
        sa.Column("encrypted_client_secret", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("salesforce_orgs", "encrypted_client_secret")
