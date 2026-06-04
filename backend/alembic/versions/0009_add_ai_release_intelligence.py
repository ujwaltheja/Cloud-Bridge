"""add ai release intelligence fields (release_readiness, risk_areas, recommendation, suggested_actions, git_diff)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('impact_analyses', sa.Column('release_readiness', sa.Integer(), nullable=True))
    op.add_column('impact_analyses', sa.Column('risk_areas', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('recommendation', sa.Text(), nullable=True))
    op.add_column('impact_analyses', sa.Column('suggested_actions', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('git_diff', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('impact_analyses', 'git_diff')
    op.drop_column('impact_analyses', 'suggested_actions')
    op.drop_column('impact_analyses', 'recommendation')
    op.drop_column('impact_analyses', 'risk_areas')
    op.drop_column('impact_analyses', 'release_readiness')
