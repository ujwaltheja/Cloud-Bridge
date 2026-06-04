from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DeploymentCreate(BaseModel):
    org_id: UUID
    retrieval_id: UUID | None = None
    comparison_id: UUID | None = None
    deployment_type: str = "validate_only"   # validate_only | quick_deploy | full_deploy
    artifact_key: str | None = None
    # Real execution options (for validation / test runs)
    check_only: bool = False
    test_level: str | None = None  # NoTestRun | RunLocalTests | RunSpecifiedTests | RunAllTestsInOrg | RunRelevantTests
    run_tests: list[str] | None = None  # for RunSpecifiedTests
    source_dir: str | None = None  # absolute or relative to project for direct deploy
    manifest_path: str | None = None
    # Optional PMD pre-check controls (enabled by default; blocking remains opt-in)
    enable_pmd_check: bool = True
    pmd_block_on_violation: bool = False
    pmd_ruleset: str | None = None
    # Optional link to the AI Release Intelligence analysis performed before this deployment
    intelligence_analysis_id: UUID | None = None
    intelligence_readiness: int | None = None
    intelligence_decision: str | None = None

class DeploymentResponse(BaseModel):
    id: UUID
    org_id: UUID
    retrieval_id: UUID | None = None
    comparison_id: UUID | None = None
    status: str
    deployment_type: str
    artifact_key: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    salesforce_deployment_id: str | None = None
    # Execution options used for this deployment job (persisted for background + history)
    options: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
