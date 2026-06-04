"""
Cloud Bridge — SQLAlchemy ORM models.

All models inherit from Base (DeclarativeBase) and TimestampMixin defined in base.py.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, GUID, TimestampMixin

# ---------------------------------------------------------------------------
# Enums (plain str constants — avoids SQLAlchemy Enum DDL portability issues)
# ---------------------------------------------------------------------------

class SalesforceOrgType:
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    DEVELOPER = "developer"
    SCRATCH = "scratch"


class SalesforceAuthMethod:
    OAUTH_WEB = "oauth_web"
    JWT = "jwt"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ---------------------------------------------------------------------------
# TaskExecution — worker observability (PR 1 priority)
# ---------------------------------------------------------------------------

class TaskExecution(Base, TimestampMixin):
    __tablename__ = "task_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    args: Mapped[dict | None] = mapped_column(JSON)
    kwargs: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    exception: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str | None] = mapped_column(String(255), index=True)


# ---------------------------------------------------------------------------
# SalesforceOrg
# ---------------------------------------------------------------------------

class SalesforceOrg(Base, TimestampMixin):
    __tablename__ = "salesforce_orgs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False)   # SalesforceOrgType values
    auth_method: Mapped[str] = mapped_column(String(50), nullable=False)  # SalesforceAuthMethod values

    # Salesforce-side identifiers
    org_id: Mapped[str | None] = mapped_column(String(255))       # 18-char Salesforce org ID
    username: Mapped[str | None] = mapped_column(String(255))
    instance_url: Mapped[str | None] = mapped_column(String(512))
    client_id: Mapped[str | None] = mapped_column(String(512))

    # Encrypted credentials (Fernet-encrypted, never stored in plaintext)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    encrypted_private_key: Mapped[str | None] = mapped_column(Text)
    encrypted_client_secret: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_connection_status: Mapped[str | None] = mapped_column(String(50))
    last_connection_error: Mapped[str | None] = mapped_column(String)

    # Relationships (cascade delete to remove related records when org is deleted)
    retrievals: Mapped[list["MetadataRetrieval"]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )
    impact_analyses: Mapped[list["ImpactAnalysis"]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# MetadataRetrieval
# ---------------------------------------------------------------------------

class MetadataRetrieval(Base, TimestampMixin):
    __tablename__ = "metadata_retrievals"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("salesforce_orgs.id"), nullable=False)

    package_xml: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False, index=True)
    artifact_key: Mapped[str | None] = mapped_column(String)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String)

    # Relationships
    org: Mapped["SalesforceOrg"] = relationship(back_populates="retrievals")
    source_comparisons: Mapped[list["MetadataComparison"]] = relationship(
        foreign_keys="MetadataComparison.source_retrieval_id", back_populates="source_retrieval"
    )
    target_comparisons: Mapped[list["MetadataComparison"]] = relationship(
        foreign_keys="MetadataComparison.target_retrieval_id", back_populates="target_retrieval"
    )


# ---------------------------------------------------------------------------
# MetadataComparison
# ---------------------------------------------------------------------------

class MetadataComparison(Base, TimestampMixin):
    __tablename__ = "metadata_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_retrieval_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("metadata_retrievals.id"), nullable=False
    )
    target_retrieval_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("metadata_retrievals.id"), nullable=False
    )
    source_org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("salesforce_orgs.id"), nullable=False
    )
    target_org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("salesforce_orgs.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    diff_summary: Mapped[dict | None] = mapped_column(JSON)
    diff_artifact_key: Mapped[str | None] = mapped_column(String)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String)

    # Relationships
    source_retrieval: Mapped["MetadataRetrieval"] = relationship(
        foreign_keys=[source_retrieval_id], back_populates="source_comparisons"
    )
    target_retrieval: Mapped["MetadataRetrieval"] = relationship(
        foreign_keys=[target_retrieval_id], back_populates="target_comparisons"
    )


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------

class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("salesforce_orgs.id"), nullable=False)
    retrieval_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("metadata_retrievals.id"))
    comparison_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("metadata_comparisons.id"))

    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    deployment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(String)

    # Persisted execution options for the deployment "job" (check_only, test level etc).
    # Allows background Celery execution to rehydrate the exact request without passing all args to task.
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String)
    salesforce_deployment_id: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    org: Mapped["SalesforceOrg"] = relationship(back_populates="deployments")


# ---------------------------------------------------------------------------
# ImpactAnalysis — Deployment Impact Analysis & Dependency Intelligence
# ---------------------------------------------------------------------------

class ImpactAnalysis(Base, TimestampMixin):
    """
    Stores impact analysis results for metadata changes.
    Analyzes dependencies and predicts deployment impact.
    """
    __tablename__ = "impact_analyses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("salesforce_orgs.id"), nullable=False)
    retrieval_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("metadata_retrievals.id"))
    comparison_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("metadata_comparisons.id"))
    
    # Analysis metadata
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'pre_deployment', 'change_set', 'full_scan'
    
    # Changed metadata items (input)
    changed_items: Mapped[dict] = mapped_column(JSON, nullable=False)  # {type: [names]}
    
    # Impact results
    impacted_components: Mapped[dict | None] = mapped_column(JSON)  # Detected dependencies
    risk_score: Mapped[int | None] = mapped_column()  # 0-100
    risk_level: Mapped[str | None] = mapped_column(String(20))  # 'low', 'medium', 'high', 'critical'

    # AI Risk Scoring + Go/No-Go Decision
    release_score: Mapped[int | None] = mapped_column()  # 0-100 (higher is better / safer to release)
    go_no_go_decision: Mapped[str | None] = mapped_column(String(20))  # 'GO', 'HOLD', or 'NO-GO'
    decision_reasoning: Mapped[str | None] = mapped_column(Text)

    # AI Release Intelligence (rich pre-deployment AI layer - Best overall)
    release_readiness: Mapped[int | None] = mapped_column()  # 0-100 % (primary readiness score for "Release Readiness: XX%")
    risk_areas: Mapped[list[dict] | None] = mapped_column(JSON)  # e.g. [{"name": "...", "severity": "high|medium|low", "details": "..."}]
    recommendation: Mapped[str | None] = mapped_column(Text)
    suggested_actions: Mapped[list[str] | None] = mapped_column(JSON)  # e.g. ["approve", "hold", "suggest_fixes", "generate_release_plan"]

    # Rich inputs captured for intelligence (Git diff is key per spec)
    git_diff: Mapped[str | None] = mapped_column(Text)
    
    # AI-generated insights
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_recommendations: Mapped[list[str] | None] = mapped_column(JSON)
    predicted_issues: Mapped[list[dict] | None] = mapped_column(JSON)
    # Whether the AI insights (summary/recommendations/predicted_issues) came from a real LLM call
    # (vs the hardcoded fallback). Persisted so UI can show "powered by LLM" badge consistently.
    llm_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    
    # Deployment package
    suggested_package: Mapped[dict | None] = mapped_column(JSON)  # Auto-generated deployment manifest
    
    # AI Dependency Graph + Auto Package Builder
    dependency_graph: Mapped[dict | None] = mapped_column(JSON)  # Full dependency graph structure
    missing_dependencies: Mapped[list[dict] | None] = mapped_column(JSON)  # Missing components detected
    deployment_order: Mapped[list[str] | None] = mapped_column(JSON)  # Ordered list of components for deployment
    validation_order: Mapped[list[str] | None] = mapped_column(JSON)  # Ordered list for validation
    auto_package_generated: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    package_metadata: Mapped[dict | None] = mapped_column(JSON)  # Package generation metadata
    
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String)
    
    # Relationships
    org: Mapped["SalesforceOrg"] = relationship(back_populates="impact_analyses")
    dependencies: Mapped[list["MetadataDependency"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class MetadataDependency(Base, TimestampMixin):
    """
    Stores individual metadata dependencies discovered during analysis.
    Represents the dependency graph edges.
    """
    __tablename__ = "metadata_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("impact_analyses.id"), nullable=False)
    
    # Source (the changed item)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Target (the impacted item)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Dependency metadata
    dependency_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'direct', 'indirect', 'reference'
    confidence: Mapped[float | None] = mapped_column()  # 0.0-1.0 confidence score
    
    # Additional context
    details: Mapped[dict | None] = mapped_column(JSON)  # Line numbers, field names, etc.
    
    # Relationships
    analysis: Mapped["ImpactAnalysis"] = relationship(back_populates="dependencies")
