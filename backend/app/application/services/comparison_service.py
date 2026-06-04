"""
Comparison Engine Service (Pushed toward 100%)

Now with richer diff logic and better structure for the prototype.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.db.models import MetadataComparison, MetadataRetrieval
from app.infrastructure.di import get_artifact_store

artifact_store: ArtifactStore = get_artifact_store()


class ComparisonService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_comparison(
        self, 
        source_retrieval_id: uuid.UUID, 
        target_retrieval_id: uuid.UUID
    ) -> MetadataComparison:
        source = await self._get_retrieval(source_retrieval_id)
        target = await self._get_retrieval(target_retrieval_id)
        if not source:
            raise ValueError(f"Source retrieval {source_retrieval_id} not found")
        if not target:
            raise ValueError(f"Target retrieval {target_retrieval_id} not found")

        comparison = MetadataComparison(
            source_retrieval_id=source_retrieval_id,
            target_retrieval_id=target_retrieval_id,
            source_org_id=source.org_id,
            target_org_id=target.org_id,
            status="pending",
        )
        self.db.add(comparison)
        await self.db.commit()
        return await self._load_fresh(comparison.id)

    async def _load_fresh(self, comparison_id: uuid.UUID) -> MetadataComparison:
        """Re-SELECT the comparison row, populating every column in-memory.

        Using populate_existing=True forces SQLAlchemy to overwrite every
        attribute on the in-memory object with the DB row values, even if
        those attributes were not marked as expired.  This prevents the
        MissingGreenlet error that occurs when FastAPI's Pydantic serializer
        accesses server-default columns (updated_at) outside of an async
        SQLAlchemy context.
        """
        result = await self.db.execute(
            select(MetadataComparison)
            .where(MetadataComparison.id == comparison_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def run_comparison(self, comparison_id: uuid.UUID) -> MetadataComparison:
        comp = await self.get_comparison(comparison_id)
        if not comp:
            raise ValueError("Comparison not found")

        source = await self._get_retrieval(comp.source_retrieval_id)
        target = await self._get_retrieval(comp.target_retrieval_id)

        if not source or not target:
            comp.status = "failed"
            comp.error_message = "One or both retrievals not found"
            await self.db.commit()
            return await self._load_fresh(comp.id)

        try:
            comp.status = "running"
            comp.started_at = datetime.utcnow()
            await self.db.commit()

            source_data = await self._load_artifact(source.artifact_key)
            target_data = await self._load_artifact(target.artifact_key)

            # Richer prototype-level diff
            diff_result = self._compute_rich_diff(source_data, target_data)

            diff_key = f"comparisons/{comp.id}/diff.json"
            diff_content = {
                "comparison_id": str(comp.id),
                "source_retrieval_id": str(comp.source_retrieval_id),
                "target_retrieval_id": str(comp.target_retrieval_id),
                "summary": diff_result["summary"],
                "added": diff_result["added"],
                "removed": diff_result["removed"],
                "modified": diff_result["modified"],
                "generated_at": datetime.utcnow().isoformat(),
            }

            await artifact_store.save(
                diff_key,
                str(diff_content).encode("utf-8"),
                "application/json"
            )

            comp.diff_summary = diff_result["summary"]
            comp.diff_artifact_key = diff_key
            comp.status = "completed"
            comp.completed_at = datetime.utcnow()

            await self.db.commit()
            return await self._load_fresh(comp.id)

        except Exception as e:
            comp.status = "failed"
            comp.error_message = str(e)
            comp.completed_at = datetime.utcnow()
            await self.db.commit()
            return await self._load_fresh(comp.id)

    def _compute_rich_diff(self, source_data: dict, target_data: dict) -> dict:
        """Prototype-level but richer diff logic."""
        source_classes = self._extract_class_names(source_data)
        target_classes = self._extract_class_names(target_data)

        added = sorted(target_classes - source_classes)
        removed = sorted(source_classes - target_classes)

        # Simple modified detection (prototype)
        # common = source_classes & target_classes  # Reserved for future use
        modified = []  # Could compare content hashes later

        summary = {
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
        }

        return {
            "summary": summary,
            "added": added[:50],
            "removed": removed[:50],
            "modified": modified[:50],
        }

    def _extract_class_names(self, data: dict) -> set:
        if not data:
            return set()
        if "apex_classes" in data:
            classes = data["apex_classes"]
            if classes and isinstance(classes[0], dict):
                return {c.get("name") for c in classes if c.get("name")}
            return set(classes)
        return set()

    async def get_comparison(self, comparison_id: uuid.UUID):
        result = await self.db.execute(
            select(MetadataComparison).where(MetadataComparison.id == comparison_id)
        )
        return result.scalar_one_or_none()

    async def _get_retrieval(self, retrieval_id: uuid.UUID):
        result = await self.db.execute(
            select(MetadataRetrieval).where(MetadataRetrieval.id == retrieval_id)
        )
        return result.scalar_one_or_none()

    async def _load_artifact(self, key: str | None) -> dict[str, Any]:
        if not key:
            return {}
        try:
            content = await artifact_store.get(key)
            import ast
            return ast.literal_eval(content.decode("utf-8"))
        except Exception:
            return {}
