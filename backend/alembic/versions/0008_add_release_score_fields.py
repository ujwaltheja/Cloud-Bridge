"""add release score and go/no-go fields

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-03 09:51:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add release score, go/no-go decision, and llm_used fields."""
    op.add_column('impact_analyses', sa.Column('release_score', sa.Integer(), nullable=True))
    op.add_column('impact_analyses', sa.Column('go_no_go_decision', sa.String(length=20), nullable=True))
    op.add_column('impact_analyses', sa.Column('decision_reasoning', sa.Text(), nullable=True))
    op.add_column('impact_analyses', sa.Column('llm_used', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Remove release score, go/no-go decision, and llm_used fields."""
    op.drop_column('impact_analyses', 'llm_used')
    op.drop_column('impact_analyses', 'decision_reasoning')
    op.drop_column('impact_analyses', 'go_no_go_decision')
    op.drop_column('impact_analyses', 'release_score')

# Made with Bob
