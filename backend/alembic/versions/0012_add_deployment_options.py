"""Add options JSON column to deployments table

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-05 19:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deployments", sa.Column("options", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("deployments", "options")
