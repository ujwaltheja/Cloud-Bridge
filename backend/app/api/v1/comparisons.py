"""
Comparison Engine API
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.application.services.comparison_service import ComparisonService
from app.schemas.comparison import ComparisonCreate, ComparisonResponse

router = APIRouter(prefix="/comparisons", tags=["Comparison Engine"])

@router.post("", response_model=ComparisonResponse)
async def create_comparison(
    payload: ComparisonCreate,
    db: AsyncSession = Depends(get_db_session),
):
    service = ComparisonService(db)
    comparison = await service.create_comparison(
        payload.source_retrieval_id,
        payload.target_retrieval_id
    )
    # Run comparison synchronously for prototype
    updated = await service.run_comparison(comparison.id)
    return updated

@router.get("", response_model=list[ComparisonResponse])
async def list_comparisons(db: AsyncSession = Depends(get_db_session)):
    # For prototype, return empty list (we can expand later)
    return []

@router.get("/{comparison_id}", response_model=ComparisonResponse)
async def get_comparison(comparison_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = ComparisonService(db)
    comp = await service.get_comparison(comparison_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comp
