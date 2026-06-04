"""
Impact Analysis API Endpoints

REST API for deployment impact analysis and dependency intelligence.
"""

from uuid import UUID
from io import BytesIO

import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.application.services.impact_analysis_service import ImpactAnalysisService
from app.application.services.report_pdf_service import ReportPDFService
from app.schemas.impact_analysis import (
    ImpactAnalysisCreate,
    ImpactAnalysisRun,
    ImpactAnalysisSchema,
    ImpactAnalysisSummary,
    ImpactAnalysisList,
    DependencyGraph,
)

router = APIRouter(prefix="/impact-analysis", tags=["Impact Analysis"])


@router.post(
    "",
    response_model=ImpactAnalysisSchema,
    status_code=201,
    summary="Create impact analysis",
    description="Create a new impact analysis for metadata changes",
)
async def create_analysis(
    payload: ImpactAnalysisCreate,
    db: AsyncSession = Depends(get_db_session),
) -> ImpactAnalysisSchema:
    """Create a new impact analysis."""
    logger = logging.getLogger(__name__)
    logger.info(f"[API] Creating analysis for org={payload.org_id}, retrieval={payload.retrieval_id}, type={payload.analysis_type}")
    service = ImpactAnalysisService(db)
    analysis = await service.create_analysis(payload)
    logger.info(f"[API] Analysis created id={analysis.id}, status={analysis.status}, llm_used={getattr(analysis, 'llm_used', None)}")
    try:
        validated = ImpactAnalysisSchema.model_validate(analysis)
        logger.info(f"[API] model_validate succeeded for create, llm_used in response={validated.llm_used}")
        return validated
    except Exception as e:
        logger.exception("[API] model_validate FAILED in create_analysis")
        raise


@router.post(
    "/{analysis_id}/run",
    response_model=ImpactAnalysisSchema,
    summary="Run impact analysis",
    description="Execute impact analysis with dependency detection and AI insights",
)
async def run_analysis(
    analysis_id: UUID,
    include_ai_insights: bool = Query(default=True, description="Generate AI insights"),
    build_package: bool = Query(default=True, description="Build deployment package"),
    db: AsyncSession = Depends(get_db_session),
) -> ImpactAnalysisSchema:
    """Run impact analysis."""
    logger = logging.getLogger(__name__)
    logger.info(f"[API] /run called for analysis_id={analysis_id}, include_ai={include_ai_insights}")
    service = ImpactAnalysisService(db)
    try:
        analysis = await service.run_analysis(
            analysis_id,
            include_ai_insights=include_ai_insights,
            build_package=build_package,
        )
        logger.info(f"[API] run completed for {analysis_id}, status={analysis.status}, llm_used={analysis.llm_used}")
        return ImpactAnalysisSchema.model_validate(analysis)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"[API] run_analysis failed for {analysis_id}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post(
    "/quick-analyze",
    response_model=ImpactAnalysisSchema,
    status_code=201,
    summary="Quick analyze (create + run)",
    description="Create and immediately run impact analysis in one request",
)
async def quick_analyze(
    payload: ImpactAnalysisCreate,
    include_ai_insights: bool = Query(default=True),
    build_package: bool = Query(default=True),
    db: AsyncSession = Depends(get_db_session),
) -> ImpactAnalysisSchema:
    """Create and run impact analysis in one step."""
    logger = logging.getLogger(__name__)
    logger.info(f"[API] quick-analyze called (legacy path) for org={payload.org_id}")
    service = ImpactAnalysisService(db)
    
    # Create analysis
    analysis = await service.create_analysis(payload)
    
    # Run analysis
    try:
        analysis = await service.run_analysis(
            analysis.id,
            include_ai_insights=include_ai_insights,
            build_package=build_package,
        )
        logger.info(f"[API] quick-analyze completed, llm_used={analysis.llm_used}")
        return ImpactAnalysisSchema.model_validate(analysis)
    except Exception as e:
        logger.exception("[API] quick-analyze failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get(
    "",
    response_model=ImpactAnalysisList,
    summary="List impact analyses",
    description="Get paginated list of impact analyses",
)
async def list_analyses(
    org_id: UUID | None = Query(default=None, description="Filter by org ID"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> ImpactAnalysisList:
    """List impact analyses with pagination."""
    service = ImpactAnalysisService(db)
    analyses, total = await service.list_analyses(org_id, page, page_size)
    
    summaries = [
        ImpactAnalysisSummary(
            id=a.id,
            org_id=a.org_id,
            retrieval_id=a.retrieval_id,
            comparison_id=a.comparison_id,
            status=a.status,
            analysis_type=a.analysis_type,
            risk_level=a.risk_level,
            risk_score=a.risk_score,
            release_score=a.release_score,
            go_no_go_decision=a.go_no_go_decision,
            release_readiness=a.release_readiness,
            recommendation=a.recommendation,
            risk_areas_count=len(a.risk_areas) if a.risk_areas else 0,
            changed_items_count=sum(len(v) for v in a.changed_items.values()),
            impacted_components_count=sum(
                len(v) for v in (a.impacted_components or {}).values()
            ),
            created_at=a.created_at,
            completed_at=a.completed_at,
            llm_used=a.llm_used,
        )
        for a in analyses
    ]
    logger.info(f"[API] Listed {len(summaries)} analyses for org={org_id}, first few llm_used: {[s.llm_used for s in summaries[:3]]}")
    
    return ImpactAnalysisList(
        analyses=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{analysis_id}",
    response_model=ImpactAnalysisSchema,
    summary="Get impact analysis",
    description="Get detailed impact analysis with dependencies",
)
async def get_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ImpactAnalysisSchema:
    """Get a single impact analysis."""
    logger.info(f"[API] GET analysis detail for {analysis_id}")
    service = ImpactAnalysisService(db)
    analysis = await service.get_analysis(analysis_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    
    validated = ImpactAnalysisSchema.model_validate(analysis)
    logger.info(f"[API] GET analysis {analysis_id} returned, llm_used={validated.llm_used}")
    return validated


@router.get(
    "/{analysis_id}/graph",
    response_model=DependencyGraph,
    summary="Get dependency graph",
    description="Get dependency graph for visualization",
)
async def get_dependency_graph(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> DependencyGraph:
    """Get dependency graph for visualization."""
    logger.info(f"[API] GET graph for analysis {analysis_id}")
    service = ImpactAnalysisService(db)
    try:
        g = await service.get_dependency_graph(analysis_id)
        logger.info(f"[API] Graph for {analysis_id}: nodes={len(g.nodes)}, edges={len(g.edges)}")
        return g
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{analysis_id}/report/pdf",
    summary="Download IBM Salesforce Release Readiness PDF",
    description="Download an IBM-formatted Salesforce release readiness business report",
)
async def download_release_intelligence_pdf(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    service = ImpactAnalysisService(db)
    analysis = await service.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    pdf_service = ReportPDFService()
    pdf_bytes = pdf_service.generate_release_intelligence_pdf(analysis)
    filename = f"ibm-salesforce-release-readiness-{analysis_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{analysis_id}",
    status_code=204,
    summary="Delete impact analysis",
    description="Delete an impact analysis and its dependencies",
)
async def delete_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete an impact analysis."""
    service = ImpactAnalysisService(db)
    analysis = await service.get_analysis(analysis_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    
    await db.delete(analysis)
    await db.commit()

# Made with Bob
