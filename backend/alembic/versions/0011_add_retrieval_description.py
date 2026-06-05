"""add description to metadata retrievals

Revision ID: 0011_add_retrieval_description
Revises: 0010_add_dependency_graph_builder
Create Date: 2026-06-05 18:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_add_retrieval_description"
down_revision: Union[str, None] = "0010_add_dependency_graph_builder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("metadata_retrievals", sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("metadata_retrievals", "description")
