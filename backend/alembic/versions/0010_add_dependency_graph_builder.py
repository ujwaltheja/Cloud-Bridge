"""add dependency graph builder

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03 10:44:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to impact_analyses table for dependency graph builder
    op.add_column('impact_analyses', sa.Column('dependency_graph', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('missing_dependencies', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('deployment_order', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('validation_order', sa.JSON(), nullable=True))
    op.add_column('impact_analyses', sa.Column('auto_package_generated', sa.Boolean(), nullable=True, default=False))
    op.add_column('impact_analyses', sa.Column('package_metadata', sa.JSON(), nullable=True))
    
    # Add index for faster dependency lookups
    op.create_index('ix_metadata_dependencies_source', 'metadata_dependencies', ['source_type', 'source_name'])
    op.create_index('ix_metadata_dependencies_target', 'metadata_dependencies', ['target_type', 'target_name'])


def downgrade() -> None:
    op.drop_index('ix_metadata_dependencies_target', 'metadata_dependencies')
    op.drop_index('ix_metadata_dependencies_source', 'metadata_dependencies')
    
    op.drop_column('impact_analyses', 'package_metadata')
    op.drop_column('impact_analyses', 'auto_package_generated')
    op.drop_column('impact_analyses', 'validation_order')
    op.drop_column('impact_analyses', 'deployment_order')
    op.drop_column('impact_analyses', 'missing_dependencies')
    op.drop_column('impact_analyses', 'dependency_graph')

# Made with Bob
