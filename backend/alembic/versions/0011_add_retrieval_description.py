"""add description to metadata retrievals

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-05 18:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("metadata_retrievals", sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("metadata_retrievals", "description")
