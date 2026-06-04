"""
AI Dependency Graph + Auto Package Builder API

Endpoints for AI-powered dependency discovery and automatic package generation.
"""

import logging
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.application.services.dependency_graph_service import DependencyGraphService
from app.application.services.impact_analysis_service import ImpactAnalysisService
from app.application.services.report_pdf_service import ReportPDFService
from app.schemas.impact_analysis import (
    DependencyGraphRequest,
    DependencyGraphResponse,
    AutoPackageBuilderRequest,
    AutoPackageBuilderResponse,
    MissingDependency,
    ImpactAnalysisCreate,
)

router = APIRouter(prefix="/dependency-graph", tags=["AI Dependency Graph"])
logger = logging.getLogger(__name__)


def _normalize_auto_added_components(package_metadata: dict | None) -> list[dict] | None:
    """Normalize legacy/new auto-added metadata to response shape list[dict]."""
    if not package_metadata:
        return None

    auto_added = package_metadata.get("auto_added")
    if auto_added is None:
        return None

    if isinstance(auto_added, list):
        return auto_added

    if isinstance(auto_added, dict):
        normalized: list[dict] = []
        for dep_type, names in auto_added.items():
            if isinstance(names, list):
                normalized.append({"type": dep_type, "names": names})
        return normalized

    return None


@router.post("/build", response_model=DependencyGraphResponse)
async def build_dependency_graph(
    request: DependencyGraphRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Build AI-powered dependency graph for specified components.
    
    Discovers:
    - Direct dependencies (e.g., Flow → Apex Class)
    - Indirect dependencies (e.g., Apex → Custom Metadata)
    - Missing dependencies (e.g., Permission Sets, Profiles)
    
    Returns:
    - Visual dependency graph
    - Missing components list
    - Deployment order (topologically sorted)
    - Validation order
    - Auto-generated package.xml
    """
    try:
        # Create an impact analysis for this request
        impact_service = ImpactAnalysisService(db)
        analysis = await impact_service.create_analysis(ImpactAnalysisCreate(
            org_id=request.org_id,
            analysis_type="dependency_graph",
            changed_items=request.components,
        ))
        
        # Build the dependency graph
        graph_service = DependencyGraphService(db)
        result = await graph_service.build_dependency_graph(
            analysis_id=analysis.id,
            components=request.components,
            include_missing=request.include_missing,
            use_ai=True,
        )
        
        # Generate package.xml if requested
        package_xml = None
        auto_added = None
        
        if request.generate_package:
            all_components = dict(request.components)
            
            # Auto-add missing dependencies if they're critical
            if result["missing_dependencies"]:
                missing_deps = [
                    MissingDependency(**dep) for dep in result["missing_dependencies"]
                ]
                added = await graph_service.auto_add_missing_dependencies(
                    analysis.id, missing_deps
                )
                
                # Merge added components
                for dep_type, names in added.items():
                    if dep_type in all_components:
                        all_components[dep_type].extend(names)
                    else:
                        all_components[dep_type] = names
                
                auto_added = [
                    {"type": dep_type, "names": names}
                    for dep_type, names in added.items()
                ]
            
            # Generate package.xml
            package_xml = await graph_service.generate_package_xml(
                analysis.id, all_components, include_dependencies=True
            )
        
        # Update analysis with results
        analysis.dependency_graph = result["graph"]
        analysis.missing_dependencies = result["missing_dependencies"]
        analysis.deployment_order = result["deployment_order"]
        analysis.validation_order = result["validation_order"]
        analysis.auto_package_generated = request.generate_package
        analysis.package_metadata = {
            "auto_added_count": len(auto_added) if auto_added else 0,
            "total_components": len(result["deployment_order"]),
        }
        analysis.status = "completed"
        
        await db.commit()
        # We intentionally avoid db.refresh(analysis) here.
        # The GUID TypeDecorator + defensive UUID result processor now makes
        # refreshes safe, but we already have the id and all the data we need
        # for the response. This also avoids any transient binding issues on
        # this code path.
        
        return DependencyGraphResponse(
            analysis_id=analysis.id,
            graph=result["graph"],
            missing_dependencies=result["missing_dependencies"],
            deployment_order=result["deployment_order"],
            validation_order=result["validation_order"],
            package_xml=package_xml,
            auto_added_components=auto_added,
            stats=result["graph"]["stats"],
        )
        
    except Exception as e:
        logger.exception(f"Error building dependency graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{analysis_id}", response_model=DependencyGraphResponse)
async def get_dependency_graph(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get existing dependency graph for an analysis.
    """
    impact_service = ImpactAnalysisService(db)
    analysis = await impact_service.get_analysis(analysis_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    if not analysis.dependency_graph:
        raise HTTPException(
            status_code=404,
            detail="Dependency graph not built for this analysis"
        )
    
    # Reconstruct response from stored data
    auto_added_components = _normalize_auto_added_components(analysis.package_metadata)

    return DependencyGraphResponse(
        analysis_id=analysis.id,
        graph=analysis.dependency_graph,
        missing_dependencies=analysis.missing_dependencies or [],
        deployment_order=analysis.deployment_order or [],
        validation_order=analysis.validation_order or [],
        package_xml=analysis.suggested_package.get("package_xml") if analysis.suggested_package else None,
        auto_added_components=auto_added_components,
        stats=analysis.dependency_graph.get("stats", {}) if analysis.dependency_graph else {},
    )


@router.get("/{analysis_id}/report/pdf")
async def download_dependency_graph_pdf(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Download IBM Salesforce dependency and package PDF report."""
    impact_service = ImpactAnalysisService(db)
    analysis = await impact_service.get_analysis(analysis_id)

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    pdf_service = ReportPDFService()
    pdf_bytes = pdf_service.generate_dependency_graph_pdf(analysis)
    filename = f"ibm-salesforce-dependency-package-{analysis_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/auto-package", response_model=AutoPackageBuilderResponse)
async def build_auto_package(
    request: AutoPackageBuilderRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Auto-build deployment package with dependency resolution.
    
    Features:
    - Automatically adds missing dependencies
    - Generates proper deployment order
    - Includes related profiles and permission sets
    - Provides warnings about potential issues
    """
    try:
        impact_service = ImpactAnalysisService(db)
        analysis = await impact_service.get_analysis(request.analysis_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        graph_service = DependencyGraphService(db)
        
        # Get all components including dependencies
        all_components = dict(analysis.changed_items)
        added_dependencies = []
        warnings = []
        
        # Auto-add missing dependencies if requested
        if request.auto_add_missing and analysis.missing_dependencies:
            missing_deps = [
                MissingDependency(**dep) for dep in analysis.missing_dependencies
            ]
            
            # Filter based on user preferences
            filtered_deps = []
            for dep in missing_deps:
                if dep.type == "Profile" and not request.include_profiles:
                    warnings.append(f"Skipped Profile: {dep.name} (disabled by user)")
                    continue
                if dep.type == "PermissionSet" and not request.include_permission_sets:
                    warnings.append(f"Skipped PermissionSet: {dep.name} (disabled by user)")
                    continue
                filtered_deps.append(dep)
            
            # Add filtered dependencies
            added = await graph_service.auto_add_missing_dependencies(
                request.analysis_id, filtered_deps
            )
            
            for dep_type, names in added.items():
                if dep_type in all_components:
                    all_components[dep_type].extend(names)
                else:
                    all_components[dep_type] = names
            
            added_dependencies = filtered_deps
        
        # Generate package.xml
        package_xml = await graph_service.generate_package_xml(
            request.analysis_id, all_components, include_dependencies=True
        )
        
        # Get deployment and validation order
        deployment_order = analysis.deployment_order or []
        validation_order = analysis.validation_order or []
        
        # Estimate deployment time (rough estimate: 30 seconds per component)
        total_components = sum(len(names) for names in all_components.values())
        estimated_time = max(5, total_components * 0.5)  # At least 5 minutes
        
        # Add warnings for high-risk components
        if "ApexTrigger" in all_components:
            warnings.append("Apex Triggers detected - ensure proper test coverage")
        if "Flow" in all_components:
            warnings.append("Flows detected - validate all flow versions are active")
        if len(all_components) > 50:
            warnings.append(f"Large deployment ({total_components} components) - consider splitting")
        
        # Update analysis
        analysis.suggested_package = {
            "package_xml": package_xml,
            "components": all_components,
            "auto_added": [dep.model_dump() for dep in added_dependencies],
        }
        analysis.auto_package_generated = True
        
        await db.commit()
        
        return AutoPackageBuilderResponse(
            package_xml=package_xml,
            components=all_components,
            deployment_order=deployment_order,
            validation_order=validation_order,
            added_dependencies=added_dependencies,
            warnings=warnings,
            estimated_deployment_time_minutes=int(estimated_time),
        )
        
    except Exception as e:
        logger.exception(f"Error building auto package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{analysis_id}/missing-dependencies/add")
async def add_missing_dependencies(
    analysis_id: UUID,
    dependency_types: list[str],
    db: AsyncSession = Depends(get_db_session),
):
    """
    Manually add specific missing dependency types to the package.
    
    Example: ["PermissionSet", "CustomMetadata"]
    """
    try:
        impact_service = ImpactAnalysisService(db)
        analysis = await impact_service.get_analysis(analysis_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        if not analysis.missing_dependencies:
            return {"message": "No missing dependencies to add", "added": []}
        
        # Filter missing dependencies by requested types
        missing_deps = [
            MissingDependency(**dep)
            for dep in analysis.missing_dependencies
            if dep["type"] in dependency_types
        ]
        
        if not missing_deps:
            return {
                "message": f"No missing dependencies of types {dependency_types}",
                "added": []
            }
        
        # Add them to the package
        graph_service = DependencyGraphService(db)
        added = await graph_service.auto_add_missing_dependencies(
            analysis_id, missing_deps
        )
        
        # Update analysis
        current_components = dict(analysis.changed_items)
        for dep_type, names in added.items():
            if dep_type in current_components:
                current_components[dep_type].extend(names)
            else:
                current_components[dep_type] = names
        
        analysis.changed_items = current_components
        
        # Regenerate package
        package_xml = await graph_service.generate_package_xml(
            analysis_id, current_components, include_dependencies=True
        )
        
        if analysis.suggested_package:
            analysis.suggested_package["package_xml"] = package_xml
            analysis.suggested_package["components"] = current_components
        
        await db.commit()
        
        return {
            "message": f"Added {len(missing_deps)} missing dependencies",
            "added": added,
            "updated_package": package_xml,
        }
        
    except Exception as e:
        logger.exception(f"Error adding missing dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Made with Bob
