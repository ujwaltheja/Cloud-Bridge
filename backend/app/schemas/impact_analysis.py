"""
Impact Analysis Schemas

Pydantic models for deployment impact analysis and dependency intelligence.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class ImpactAnalysisCreate(BaseModel):
    """Request to create a new impact analysis."""
    org_id: UUID
    retrieval_id: UUID | None = None
    comparison_id: UUID | None = None
    analysis_type: str = Field(
        default="pre_deployment",
        description="Type of analysis: pre_deployment, change_set, full_scan"
    )
    changed_items: dict[str, list[str]] = Field(
        ...,
        description="Changed metadata items grouped by type",
        examples=[{
            "ApexClass": ["AccountTriggerHandler", "OpportunityService"],
            "Flow": ["Opportunity_Approval_Flow"]
        }]
    )
    git_diff: str | None = Field(
        default=None,
        description="Optional Git diff or change summary to provide richer context for AI Release Intelligence (key input per spec)"
    )
    build_dependency_graph: bool = Field(
        default=True,
        description="Enable AI dependency graph builder to discover and visualize dependencies"
    )
    auto_add_missing: bool = Field(
        default=False,
        description="Automatically add missing dependencies to deployment package"
    )


class ImpactAnalysisRun(BaseModel):
    """Request to run impact analysis with AI insights."""
    analysis_id: UUID
    include_ai_insights: bool = Field(default=True, description="Generate AI-powered recommendations")
    build_package: bool = Field(default=True, description="Auto-generate deployment package")


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class MetadataDependencySchema(BaseModel):
    """Individual metadata dependency."""
    id: UUID
    analysis_id: UUID
    source_type: str
    source_name: str
    target_type: str
    target_name: str
    dependency_type: str  # 'direct', 'indirect', 'reference'
    confidence: float | None = None
    details: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ImpactAnalysisSchema(BaseModel):
    """Complete impact analysis result."""
    id: UUID
    org_id: UUID
    retrieval_id: UUID | None = None
    comparison_id: UUID | None = None
    status: str
    analysis_type: str
    changed_items: dict[str, list[str]]
    impacted_components: dict | None = None
    risk_score: int | None = None
    risk_level: str | None = None
    release_score: int | None = Field(default=None, description="Release score 0-100 (higher is better)")
    go_no_go_decision: str | None = Field(default=None, description="GO, HOLD, or NO-GO")
    decision_reasoning: str | None = Field(default=None, description="Reasoning for Go/No-Go decision")
    # AI Release Intelligence outputs (primary new layer)
    release_readiness: int | None = Field(default=None, description="Release Readiness percentage 0-100 (higher = more ready/safer)")
    risk_areas: list[dict] | None = Field(default=None, description="Structured risk areas e.g. [{'name': 'Opportunity Trigger', 'severity': 'high', 'details': '...'}]")
    recommendation: str | None = Field(default=None, description="High-level recommendation e.g. 'Deploy after dependency fix'")
    suggested_actions: list[str] | None = Field(default=None, description="Actionable next steps e.g. ['approve', 'hold', 'suggest_fixes', 'generate_release_plan']")
    git_diff: str | None = None
    ai_summary: str | None = None
    ai_recommendations: list[str] | None = None
    predicted_issues: list[dict] | None = None
    suggested_package: dict | None = None
    # AI Dependency Graph + Auto Package Builder
    dependency_graph: dict | None = Field(default=None, description="Full dependency graph structure with nodes and edges")
    missing_dependencies: list[dict] | None = Field(default=None, description="Missing components detected by AI")
    deployment_order: list[str] | None = Field(default=None, description="AI-generated deployment order")
    validation_order: list[str] | None = Field(default=None, description="AI-generated validation order")
    auto_package_generated: bool | None = Field(default=None, description="Whether package was auto-generated")
    package_metadata: dict | None = Field(default=None, description="Package generation metadata")
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    dependencies: list[MetadataDependencySchema] = []
    llm_used: bool | None = None

    class Config:
        from_attributes = True


class ImpactAnalysisSummary(BaseModel):
    """Lightweight summary for list views."""
    id: UUID
    org_id: UUID
    retrieval_id: UUID | None = None
    comparison_id: UUID | None = None
    status: str
    analysis_type: str
    risk_level: str | None = None
    risk_score: int | None = None
    release_score: int | None = None
    go_no_go_decision: str | None = None
    # Lightweight AI Release Intelligence for list/history views
    release_readiness: int | None = None
    recommendation: str | None = None
    risk_areas_count: int | None = None
    changed_items_count: int
    impacted_components_count: int
    created_at: datetime
    completed_at: datetime | None = None
    llm_used: bool | None = None


class ImpactAnalysisList(BaseModel):
    """Paginated list of impact analyses."""
    analyses: list[ImpactAnalysisSummary]
    total: int
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Dependency Graph Schemas
# ---------------------------------------------------------------------------

class DependencyNode(BaseModel):
    """Node in the dependency graph visualization."""
    id: str
    type: str
    name: str
    is_changed: bool = False
    is_impacted: bool = False
    risk_level: str | None = None


class DependencyEdge(BaseModel):
    """Edge in the dependency graph visualization."""
    source: str
    target: str
    dependency_type: str
    confidence: float | None = None


class DependencyGraph(BaseModel):
    """Complete dependency graph for visualization."""
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
    stats: dict = Field(
        default_factory=dict,
        description="Graph statistics (node count, edge count, etc.)"
    )


# ---------------------------------------------------------------------------
# AI Insight Schemas
# ---------------------------------------------------------------------------

class PredictedIssue(BaseModel):
    """AI-predicted deployment issue."""
    severity: str  # 'low', 'medium', 'high', 'critical'
    component: str
    issue_type: str
    description: str
    recommendation: str
    confidence: float


class DeploymentPackage(BaseModel):
    """Auto-generated deployment package."""
    package_xml: str
    components: dict[str, list[str]]
    test_classes: list[str] = []
    deployment_order: list[str] = []
    estimated_duration_minutes: int | None = None

# Made with Bob


# ---------------------------------------------------------------------------
# AI Dependency Graph + Auto Package Builder Schemas
# ---------------------------------------------------------------------------

class DependencyGraphRequest(BaseModel):
    """Request to build AI-powered dependency graph for specific components."""
    org_id: UUID
    components: dict[str, list[str]] = Field(
        ...,
        description="Components to analyze for dependencies",
        examples=[{
            "Flow": ["Opportunity_Approval_Flow"],
            "ApexClass": ["OpportunityTriggerHandler"]
        }]
    )
    include_missing: bool = Field(
        default=True,
        description="Detect and report missing dependencies"
    )
    generate_package: bool = Field(
        default=True,
        description="Auto-generate deployment package with proper ordering"
    )


class MissingDependency(BaseModel):
    """A missing dependency detected by AI."""
    type: str = Field(description="Metadata type (e.g., PermissionSet, CustomMetadata)")
    name: str = Field(description="Component name")
    required_by: list[str] = Field(description="Components that require this dependency")
    severity: str = Field(description="Impact severity: critical, high, medium, low")
    auto_addable: bool = Field(default=True, description="Can be automatically added to package")
    reason: str = Field(description="Why this dependency is needed")


class DependencyGraphResponse(BaseModel):
    """Response with full AI-powered dependency graph and auto-generated package."""
    analysis_id: UUID
    graph: DependencyGraph = Field(description="Visual dependency graph")
    missing_dependencies: list[MissingDependency] = Field(
        default_factory=list,
        description="Missing components detected by AI"
    )
    deployment_order: list[str] = Field(
        default_factory=list,
        description="AI-optimized deployment order (topological sort)"
    )
    validation_order: list[str] = Field(
        default_factory=list,
        description="AI-optimized validation order"
    )
    package_xml: str | None = Field(
        default=None,
        description="Auto-generated package.xml with all dependencies"
    )
    auto_added_components: list[dict] | None = Field(
        default=None,
        description="Components automatically added to resolve dependencies"
    )
    stats: dict = Field(
        default_factory=dict,
        description="Statistics about the dependency analysis"
    )


class AutoPackageBuilderRequest(BaseModel):
    """Request to auto-build deployment package with dependency resolution."""
    analysis_id: UUID
    auto_add_missing: bool = Field(
        default=True,
        description="Automatically add missing dependencies to package"
    )
    include_profiles: bool = Field(
        default=True,
        description="Include related profiles in package"
    )
    include_permission_sets: bool = Field(
        default=True,
        description="Include related permission sets in package"
    )


class AutoPackageBuilderResponse(BaseModel):
    """Response from auto package builder."""
    package_xml: str = Field(description="Generated package.xml")
    components: dict[str, list[str]] = Field(description="All components in package")
    deployment_order: list[str] = Field(description="Deployment order")
    validation_order: list[str] = Field(description="Validation order")
    added_dependencies: list[MissingDependency] = Field(
        default_factory=list,
        description="Dependencies that were auto-added"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about the package"
    )
    estimated_deployment_time_minutes: int | None = None
