"""add impact analysis tables

Revision ID: 0007_impact_analysis
Revises: 0006_org_client_secret
Create Date: 2026-06-03 08:29:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create impact_analyses table
    op.create_table(
        'impact_analyses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('retrieval_id', sa.UUID(), nullable=True),
        sa.Column('comparison_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=False),
        sa.Column('changed_items', sa.JSON(), nullable=False),
        sa.Column('impacted_components', sa.JSON(), nullable=True),
        sa.Column('risk_score', sa.Integer(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('ai_recommendations', sa.JSON(), nullable=True),
        sa.Column('predicted_issues', sa.JSON(), nullable=True),
        sa.Column('suggested_package', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['salesforce_orgs.id'], ),
        sa.ForeignKeyConstraint(['retrieval_id'], ['metadata_retrievals.id'], ),
        sa.ForeignKeyConstraint(['comparison_id'], ['metadata_comparisons.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_impact_analyses_status'), 'impact_analyses', ['status'], unique=False)

    # Create metadata_dependencies table
    op.create_table(
        'metadata_dependencies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('analysis_id', sa.UUID(), nullable=False),
        sa.Column('source_type', sa.String(length=100), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('target_type', sa.String(length=100), nullable=False),
        sa.Column('target_name', sa.String(length=255), nullable=False),
        sa.Column('dependency_type', sa.String(length=50), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['impact_analyses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metadata_dependencies_source_type'), 'metadata_dependencies', ['source_type'], unique=False)
    op.create_index(op.f('ix_metadata_dependencies_source_name'), 'metadata_dependencies', ['source_name'], unique=False)
    op.create_index(op.f('ix_metadata_dependencies_target_type'), 'metadata_dependencies', ['target_type'], unique=False)
    op.create_index(op.f('ix_metadata_dependencies_target_name'), 'metadata_dependencies', ['target_name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_metadata_dependencies_target_name'), table_name='metadata_dependencies')
    op.drop_index(op.f('ix_metadata_dependencies_target_type'), table_name='metadata_dependencies')
    op.drop_index(op.f('ix_metadata_dependencies_source_name'), table_name='metadata_dependencies')
    op.drop_index(op.f('ix_metadata_dependencies_source_type'), table_name='metadata_dependencies')
    op.drop_table('metadata_dependencies')
    op.drop_index(op.f('ix_impact_analyses_status'), table_name='impact_analyses')
    op.drop_table('impact_analyses')

# Made with Bob
