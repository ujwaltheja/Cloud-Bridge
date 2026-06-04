"""
Impact Analysis Service

Provides deployment impact analysis and dependency intelligence.
Detects metadata dependencies, calculates risk scores, and generates AI-powered insights.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.db.models import (
    ImpactAnalysis,
    MetadataDependency,
    SalesforceOrg,
    MetadataRetrieval,
)
from app.schemas.impact_analysis import (
    ImpactAnalysisCreate,
    DependencyGraph,
    DependencyNode,
    DependencyEdge,
    PredictedIssue,
    DeploymentPackage,
)

logger = logging.getLogger(__name__)


class ImpactAnalysisService:
    """Service for deployment impact analysis and dependency detection."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_analysis(self, payload: ImpactAnalysisCreate) -> ImpactAnalysis:
        """Create a new impact analysis record."""
        changed_items = payload.changed_items
        
        # If retrieval_id is provided, extract metadata from the retrieval package
        if payload.retrieval_id:
            changed_items = await self._extract_metadata_from_retrieval(payload.retrieval_id)
        
        analysis = ImpactAnalysis(
            org_id=payload.org_id,
            retrieval_id=payload.retrieval_id,
            comparison_id=payload.comparison_id,
            analysis_type=payload.analysis_type,
            changed_items=changed_items,
            git_diff=payload.git_diff,
            status="pending",
        )
        self.db.add(analysis)
        await self.db.commit()

        # Reload with relationships to avoid MissingGreenlet / lazy-load errors
        # when Pydantic does ImpactAnalysisSchema.model_validate(analysis)
        # (the dependencies relationship is accessed even if empty).
        # Skip instance.refresh() which can have sqlite UUID binding quirks in some aiosqlite+SA combos;
        # the full re-fetch below always works and populates fresh state + relationships.
        result = await self.db.execute(
            select(ImpactAnalysis)
            .where(ImpactAnalysis.id == analysis.id)
            .options(selectinload(ImpactAnalysis.dependencies))
        )
        analysis = result.scalar_one()

        # Initialize llm_used for the response (None until run() populates it)
        analysis.llm_used = None

        logger.info(f"Created impact analysis {analysis.id} for org {payload.org_id}, llm_used={analysis.llm_used} (after selectinload reload)")
        return analysis

    async def _extract_metadata_from_retrieval(self, retrieval_id: UUID) -> dict[str, list[str]]:
        """
        Extract metadata components from a retrieval package.
        Parses the package.xml to get actual component names.
        """
        result = await self.db.execute(
            select(MetadataRetrieval).where(MetadataRetrieval.id == retrieval_id)
        )
        retrieval = result.scalar_one_or_none()
        
        if not retrieval or not retrieval.package_xml:
            logger.warning(f"Retrieval {retrieval_id} not found or has no package.xml")
            return {}
        
        # Parse package.xml to extract metadata types and members
        import xml.etree.ElementTree as ET
        
        changed_items: dict[str, list[str]] = {}
        
        try:
            root = ET.fromstring(retrieval.package_xml)
            # Handle namespace (Salesforce package.xml uses default xmlns)
            ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
            
            # Find <types> blocks (prefer namespaced, fallback)
            types_list = root.findall('.//sf:types', ns)
            if not types_list:
                types_list = root.findall('.//types')
                ns = {}  # elements may not be using prefix in this doc
            
            for types_elem in types_list:
                # Get metadata type name (child may be namespaced).
                # Avoid "or <Element>" because Element.__bool__ can be falsy (triggers
                # deprecation and skips valid finds for leaf elements like <name>).
                name_elem = types_elem.find('sf:name', ns)
                if name_elem is None:
                    name_elem = types_elem.find('name', ns)
                if name_elem is None:
                    name_elem = types_elem.find('name')
                if name_elem is None or name_elem.text is None:
                    continue
                    
                metadata_type = name_elem.text
                
                # Get all members (findall returns list; non-empty list is safely truthy)
                member_elems = (
                    types_elem.findall('sf:members', ns)
                    or types_elem.findall('members', ns)
                    or types_elem.findall('members')
                )
                members = []
                for member_elem in member_elems:
                    if member_elem.text and member_elem.text != '*':
                        members.append(member_elem.text)
                
                if members:
                    changed_items[metadata_type] = members
                elif member_elems:
                    # Wildcard present (members=* or explicit empty with wildcard intent)
                    changed_items[metadata_type] = ['*']
            
            logger.info(f"Extracted {len(changed_items)} metadata types from retrieval {retrieval_id}")
            
        except Exception as e:
            logger.error(f"Failed to parse package.xml for retrieval {retrieval_id}: {e}")
            # Fallback to generic types for "complete" or unparseable manifests
            changed_items = {
                "ApexClass": ["*"],
                "ApexTrigger": ["*"],
                "Flow": ["*"],
            }
        
        return changed_items

    async def run_analysis(
        self,
        analysis_id: UUID,
        include_ai_insights: bool = True,
        build_package: bool = True,
        build_dependency_graph: bool = True,
    ) -> ImpactAnalysis:
        """
        Run complete impact analysis:
        1. Detect dependencies
        2. Build AI dependency graph (NEW)
        3. Calculate risk score
        4. Generate AI insights (optional)
        5. Build deployment package (optional)
        """
        # Load analysis
        result = await self.db.execute(
            select(ImpactAnalysis)
            .where(ImpactAnalysis.id == analysis_id)
            .options(selectinload(ImpactAnalysis.dependencies))
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        try:
            analysis.status = "running"
            analysis.started_at = datetime.utcnow()
            await self.db.commit()

            # Step 1: Detect dependencies
            logger.info(f"Detecting dependencies for analysis {analysis_id}")
            await self._detect_dependencies(analysis)

            # Step 2: Build AI Dependency Graph + Auto Package Builder
            if build_dependency_graph:
                logger.info(f"Building AI dependency graph for analysis {analysis_id}")
                await self._build_ai_dependency_graph(analysis)

            # Step 3: Calculate risk score
            logger.info(f"Calculating risk score for analysis {analysis_id}")
            await self._calculate_risk(analysis)

            # Step 4: Generate AI insights + AI Release Intelligence (LLM-powered)
            if include_ai_insights:
                logger.info(f"Generating AI Release Intelligence for analysis {analysis_id} (LLM)")
                await self._generate_ai_insights(analysis)

            # Step 5: Build deployment package
            if build_package:
                logger.info(f"Building deployment package for analysis {analysis_id}")
                await self._build_deployment_package(analysis)

            analysis.status = "completed"
            analysis.completed_at = datetime.utcnow()
            await self.db.commit()

            # Re-query with relationships loaded so that response serialization
            # (ImpactAnalysisSchema.model_validate) can access .dependencies without
            # triggering lazy-load (which fails with MissingGreenlet in async SQLite driver
            # once session context or greenlet scope ends).
            result = await self.db.execute(
                select(ImpactAnalysis)
                .where(ImpactAnalysis.id == analysis_id)
                .options(selectinload(ImpactAnalysis.dependencies))
            )
            analysis = result.scalar_one()

            logger.info(f"Completed impact analysis {analysis_id}")
            return analysis

        except Exception as e:
            analysis.status = "failed"
            analysis.error_message = str(e)
            analysis.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.error(f"Impact analysis {analysis_id} failed: {e}")
            raise

    async def _detect_dependencies(self, analysis: ImpactAnalysis) -> None:
        """
        Detect metadata dependencies for changed items.
        Uses pattern matching and metadata API queries.
        """
        changed_items = analysis.changed_items
        dependencies = []
        impacted_components = {}

        # Dependency detection rules
        for metadata_type, items in changed_items.items():
            for item_name in items:
                # Detect dependencies based on metadata type
                deps = await self._find_dependencies_for_item(
                    analysis.org_id, metadata_type, item_name
                )
                dependencies.extend(deps)

                # Group impacted components by type
                for dep in deps:
                    target_type = dep["target_type"]
                    if target_type not in impacted_components:
                        impacted_components[target_type] = []
                    if dep["target_name"] not in impacted_components[target_type]:
                        impacted_components[target_type].append(dep["target_name"])

        # Save dependencies to database
        for dep_data in dependencies:
            dep = MetadataDependency(
                analysis_id=analysis.id,
                source_type=dep_data["source_type"],
                source_name=dep_data["source_name"],
                target_type=dep_data["target_type"],
                target_name=dep_data["target_name"],
                dependency_type=dep_data["dependency_type"],
                confidence=dep_data.get("confidence", 0.9),
                details=dep_data.get("details"),
            )
            self.db.add(dep)

        analysis.impacted_components = impacted_components
        await self.db.commit()

    async def _find_dependencies_for_item(
        self, org_id: UUID, metadata_type: str, item_name: str
    ) -> list[dict[str, Any]]:
        """
        Find dependencies for a specific metadata item.
        Returns list of dependency dictionaries.
        """
        dependencies = []

        # ApexClass dependencies
        if metadata_type == "ApexClass":
            # Classes can be referenced by: Triggers, Flows, Other Classes, VF Pages
            dependencies.extend([
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "ApexTrigger",
                    "target_name": f"{item_name}Trigger",
                    "dependency_type": "reference",
                    "confidence": 0.7,
                    "details": {"reason": "Common trigger naming pattern"},
                },
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "PermissionSet",
                    "target_name": "API_User",
                    "dependency_type": "indirect",
                    "confidence": 0.6,
                    "details": {"reason": "Class may require permissions"},
                },
            ])

        # Flow dependencies
        elif metadata_type == "Flow":
            dependencies.extend([
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "ApexClass",
                    "target_name": f"{item_name.replace('_Flow', '')}Handler",
                    "dependency_type": "direct",
                    "confidence": 0.8,
                    "details": {"reason": "Flow may invoke Apex actions"},
                },
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "ProcessBuilder",
                    "target_name": item_name.replace("_Flow", "_Process"),
                    "dependency_type": "indirect",
                    "confidence": 0.5,
                    "details": {"reason": "May have been migrated from Process Builder"},
                },
            ])

        # CustomObject dependencies
        elif metadata_type == "CustomObject":
            obj_name = item_name.replace("__c", "")
            dependencies.extend([
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "ApexClass",
                    "target_name": f"{obj_name}TriggerHandler",
                    "dependency_type": "direct",
                    "confidence": 0.9,
                    "details": {"reason": "Standard trigger handler pattern"},
                },
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "ApexClass",
                    "target_name": f"{obj_name}Controller",
                    "dependency_type": "direct",
                    "confidence": 0.8,
                    "details": {"reason": "Standard controller pattern"},
                },
                {
                    "source_type": metadata_type,
                    "source_name": item_name,
                    "target_type": "PermissionSet",
                    "target_name": f"{obj_name}_Access",
                    "dependency_type": "direct",
                    "confidence": 0.85,
                    "details": {"reason": "Object permissions"},
                },
            ])

        return dependencies

    async def _calculate_risk(self, analysis: ImpactAnalysis) -> None:
        """
        Calculate risk score (0-100) based on:
        - Number of impacted components
        - Types of impacted components
        - Complexity of dependencies
        """
        impacted = analysis.impacted_components or {}
        total_impacted = sum(len(items) for items in impacted.values())

        # Base risk from impact count
        risk_score = min(total_impacted * 5, 50)

        # Add risk for critical component types
        critical_types = {"ApexTrigger": 15, "Flow": 10, "PermissionSet": 10, "Integration": 20}
        for comp_type, weight in critical_types.items():
            if comp_type in impacted:
                risk_score += min(len(impacted[comp_type]) * weight, weight * 2)

        # Cap at 100
        risk_score = min(risk_score, 100)

        # Determine risk level
        if risk_score >= 75:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        analysis.risk_score = risk_score
        analysis.risk_level = risk_level
        await self.db.commit()

    async def _gather_historical_context(self, org_id: UUID, analysis: ImpactAnalysis | None = None) -> dict[str, Any]:
        """
        Gather rich historical context for AI Release Intelligence.
        Inputs per spec: Deployment history, Failed releases, Org telemetry, Open incidents (proxy), Test history.
        """
        from sqlalchemy import func, desc
        
        context: dict[str, Any] = {
            "recent_deployment_failures": 0,
            "recent_deployment_success_rate": 100.0,
            "recent_deployments": [],  # detailed list for LLM
            "test_history": {
                "deployments_with_tests_run": 0,
                "recent_test_failures_proxy": 0,
                "average_test_coverage": 75.0,
            },
            "org_telemetry": {
                "org_type": "unknown",
                "last_connection_status": "unknown",
                "days_since_last_connection_test": 999,
            },
            "open_incidents_proxy": [],  # recent high-risk analyses or failed deploys
            "org_complexity_score": 50,
            "days_since_last_incident": 30,
        }
        
        try:
            from app.infrastructure.db.models import Deployment, SalesforceOrg
            
            # Org telemetry
            org_res = await self.db.execute(select(SalesforceOrg).where(SalesforceOrg.id == org_id))
            org = org_res.scalar_one_or_none()
            if org:
                context["org_telemetry"]["org_type"] = org.org_type
                context["org_telemetry"]["last_connection_status"] = org.last_connection_status or "unknown"
                if org.last_connection_test_at:
                    delta = (datetime.utcnow() - org.last_connection_test_at.replace(tzinfo=None)).days
                    context["org_telemetry"]["days_since_last_connection_test"] = max(0, delta)
            
            # Rich recent deployment history (last 12 for better signal)
            result = await self.db.execute(
                select(Deployment)
                .where(Deployment.org_id == org_id)
                .order_by(desc(Deployment.created_at))
                .limit(12)
            )
            recent_deployments = result.scalars().all()
            
            if recent_deployments:
                failures = [d for d in recent_deployments if d.status == 'failed']
                context["recent_deployment_failures"] = len(failures)
                context["recent_deployment_success_rate"] = round(((len(recent_deployments) - len(failures)) / len(recent_deployments)) * 100, 1)
                
                # Detailed list (safe subset) for LLM prompt
                context["recent_deployments"] = [
                    {
                        "id": str(d.id),
                        "type": d.deployment_type,
                        "status": d.status,
                        "created": d.created_at.isoformat() if d.created_at else None,
                        "completed": d.completed_at.isoformat() if d.completed_at else None,
                        "had_tests": bool((d.options or {}).get("test_level") or (d.options or {}).get("run_tests")),
                        "error": (d.error_message or "")[:200] if d.status == "failed" else None,
                    }
                    for d in recent_deployments[:8]
                ]
                
                # Test history proxy
                test_runs = [d for d in recent_deployments if (d.options or {}).get("test_level") or (d.options or {}).get("run_tests")]
                context["test_history"]["deployments_with_tests_run"] = len(test_runs)
                test_failures = [d for d in test_runs if d.status == "failed"]
                context["test_history"]["recent_test_failures_proxy"] = len(test_failures)
            
            # Recent impact analyses as "open incidents" + complexity
            result = await self.db.execute(
                select(ImpactAnalysis)
                .where(ImpactAnalysis.org_id == org_id)
                .order_by(desc(ImpactAnalysis.created_at))
                .limit(8)
            )
            recent_analyses = result.scalars().all()
            
            if recent_analyses:
                high_risk = [a for a in recent_analyses if (a.risk_score or 0) >= 60 or (a.release_score or 100) < 50]
                context["open_incidents_proxy"] = [
                    {
                        "id": str(a.id),
                        "risk": a.risk_score,
                        "release_score": a.release_score,
                        "go_no_go": a.go_no_go_decision,
                        "created": a.created_at.isoformat() if a.created_at else None,
                        "changed_types": list((a.changed_items or {}).keys())[:4],
                    }
                    for a in high_risk[:5]
                ]
                avg_risk = sum(a.risk_score or 50 for a in recent_analyses) / len(recent_analyses)
                context["org_complexity_score"] = int(avg_risk)
                # days since last "incident" proxy = last high risk or failure analysis
                if high_risk and high_risk[0].created_at:
                    context["days_since_last_incident"] = max(0, (datetime.utcnow() - high_risk[0].created_at.replace(tzinfo=None)).days)
            
            # If we have an analysis in flight, note its own changed items count for context
            if analysis:
                total_changed = sum(len(v) for v in (analysis.changed_items or {}).values())
                context["current_change_volume"] = total_changed
            
        except Exception as e:
            logger.warning(f"Failed to gather rich historical context: {e}")
        
        return context

    async def _calculate_release_score(self, analysis: ImpactAnalysis, historical_context: dict[str, Any]) -> int:
        """
        Calculate release score (0-100, higher is better).
        
        Factors:
        - Deployment success rate (30%)
        - Test coverage/history (25%)
        - Metadata complexity (20%)
        - Recent incidents (15%)
        - Org health (10%)
        """
        score = 100.0
        
        # Factor 1: Deployment success rate (30%)
        success_rate = historical_context.get("recent_deployment_success_rate", 100.0)
        score -= (100 - success_rate) * 0.3
        
        # Factor 2: Test coverage (25%)
        test_coverage = historical_context.get("average_test_coverage", 75.0)
        if test_coverage < 75:
            score -= (75 - test_coverage) * 0.25
        
        # Factor 3: Metadata complexity (20%)
        risk_score = analysis.risk_score or 50
        score -= (risk_score / 100) * 20
        
        # Factor 4: Recent incidents (15%)
        recent_failures = historical_context.get("recent_deployment_failures", 0)
        score -= min(recent_failures * 5, 15)
        
        # Factor 5: Org complexity (10%)
        org_complexity = historical_context.get("org_complexity_score", 50)
        score -= (org_complexity / 100) * 10
        
        # Ensure score is between 0 and 100
        return max(0, min(100, int(score)))


    async def _generate_ai_insights(self, analysis: ImpactAnalysis) -> None:
        """
        Generate full AI Release Intelligence using LLM (the "Best overall" pre-deployment layer).
        
        One AI layer before every deployment.
        Inputs (as much as available): Git diff, Salesforce metadata (changed_items + comparison diff),
        Deployment history + failed releases, Org telemetry, Open incidents (proxied via high-risk prior analyses),
        Test history (via deployment test options + outcomes).
        
        Outputs:
        - Release Readiness %
        - Risk Areas (structured)
        - Recommendation
        - Suggested Actions (approve / hold / suggest fixes / generate release plan + more)
        - Plus existing: Go/No-Go, summary, recommendations, predicted issues, suggested package
        """
        from app.application.services.llm_agent_service import LLMAgentService

        llm_service = LLMAgentService(self.db)

        # Gather rich historical context (deployment, test, incidents, telemetry)
        historical_context = await self._gather_historical_context(analysis.org_id, analysis)
        
        # Calculate base release score (reused for readiness)
        release_score = await self._calculate_release_score(analysis, historical_context)

        # Persist base scores
        analysis.release_score = release_score
        analysis.release_readiness = release_score  # start with same; LLM may refine

        # Build rich prompt for full AI Release Intelligence (LLM is the core)
        changed_items = analysis.changed_items or {}
        impacted = analysis.impacted_components or {}
        git_diff = (analysis.git_diff or "")[:4000]  # safety truncate for prompt

        # Try to enrich with comparison diff if present (provides "Git diff" like signal)
        comparison_diff_note = ""
        if analysis.comparison_id:
            try:
                from app.infrastructure.db.models import MetadataComparison
                comp_res = await self.db.execute(select(MetadataComparison).where(MetadataComparison.id == analysis.comparison_id))
                comp = comp_res.scalar_one_or_none()
                if comp and comp.diff_summary:
                    comparison_diff_note = f"\nCOMPARISON DIFF SUMMARY (source vs target): {json.dumps(comp.diff_summary, indent=1)}"
            except Exception:
                pass

        prompt = f"""You are an expert Salesforce Release Manager AI. Your job is to provide a single, authoritative "AI Release Intelligence" assessment that can replace manual CAB / release manager decision making for a deployment.

You must analyze ALL available signals and output a structured recommendation.

=== PRIMARY INPUTS (use every one that is present) ===
SALESFORCE METADATA (exact changed items from package/retrieval):
{json.dumps(changed_items, indent=2)}

IMPACTED / DEPENDENT COMPONENTS (auto-detected):
{json.dumps(impacted, indent=2)}

GIT DIFF / CHANGESET (if provided by user or via comparison):
{git_diff or "Not supplied (rely on metadata changed_items above)"}{comparison_diff_note}

DEPLOYMENT + TEST + FAILURE HISTORY (last deployments, which ones ran tests, failures and errors):
{json.dumps(historical_context.get("recent_deployments", []), indent=1)}

ORG TELEMETRY & HEALTH:
{json.dumps(historical_context.get("org_telemetry", {}), indent=1)}

OPEN INCIDENTS / HIGH-RISK PROXIES (recent high-risk analyses or problematic deploys):
{json.dumps(historical_context.get("open_incidents_proxy", []), indent=1)}

TEST HISTORY SIGNALS:
{json.dumps(historical_context.get("test_history", {}), indent=1)}

BASE CALCULATED READINESS (from success rate, test signals, complexity, incidents):
Base release readiness: {release_score}/100

=== YOUR TASK ===
Produce a complete AI Release Intelligence report. Be specific — reference real component names from the changed items.

Respond with ONLY valid minified JSON (no ```json, no explanations outside the object).

Required JSON shape (all fields mandatory, use sensible values):
{{
  "release_readiness": <integer 0-100 — your overall assessment after considering every signal above; can differ from the base>,
  "risk_areas": [
    {{"name": "exact component or area e.g. Opportunity Trigger", "severity": "high|medium|low", "details": "why this is risky, referencing history or dependencies"}}
  ],
  "recommendation": "short clear sentence e.g. 'Deploy after fixing CPQ dependency and adding tests for the new trigger'",
  "suggested_actions": ["approve", "hold", "suggest_fixes", "generate_release_plan", "run_more_tests", ...]  — choose 2-5 from or similar to: approve, hold, suggest_fixes, generate_release_plan. Be practical.
  "go_no_go_decision": "GO|HOLD|NO-GO",
  "decision_reasoning": "2-4 sentence explanation that references the release_readiness, specific risk_areas, and historical signals",
  "summary": "2-3 sentence deployment impact summary. Must name real components from the Changed Components list.",
  "recommendations": ["3-6 concrete, actionable mitigation or prep steps, referencing components"],
  "predicted_issues": [
    {{
      "severity": "low|medium|high|critical",
      "component": "real component name",
      "description": "what could go wrong",
      "recommendation": "how to prevent or mitigate",
      "confidence": 0.0-1.0
    }}
  ]
}}
"""

        try:
            logger.info(f"Calling real LLM for analysis {analysis.id} (model={getattr(llm_service.settings, 'llm_model', None)})")
            llm_response = await llm_service._call_llm(prompt)
            logger.info(f"LLM response received (len={len(llm_response or '')}) for analysis {analysis.id}")
            logger.info(f"[LLM] Raw LLM response preview (first 300 chars): {(llm_response or '')[:300]}")

            # Clean common LLM wrappers (```json ... ```, extra text, etc.)
            cleaned = llm_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # Try to extract the first JSON object if the model added extra text
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)

            data = json.loads(cleaned)

            logger.info(f"[LLM] Parsed data keys from LLM response: {list(data.keys()) if isinstance(data, dict) else str(type(data))}")

            # === AI Release Intelligence population (primary) ===
            if isinstance(data, dict):
                # Release Readiness (prefer the new field, fall back to release_score)
                for key in ("release_readiness", "releaseReadiness", "readiness", "release_score"):
                    val = data.get(key)
                    if isinstance(val, (int, float)):
                        analysis.release_readiness = int(val)
                        if key in ("release_readiness", "readiness"):
                            break
                if analysis.release_readiness is None:
                    analysis.release_readiness = analysis.release_score or release_score

                # Structured Risk Areas (list of objects or strings)
                ra = data.get("risk_areas") or data.get("riskAreas") or data.get("risks")
                if isinstance(ra, list):
                    normalized_areas = []
                    for item in ra:
                        if isinstance(item, dict):
                            normalized_areas.append({
                                "name": item.get("name") or item.get("area") or item.get("component", "Unknown"),
                                "severity": item.get("severity", "medium"),
                                "details": item.get("details") or item.get("description") or item.get("why", ""),
                            })
                        elif isinstance(item, str):
                            normalized_areas.append({"name": item, "severity": "medium", "details": ""})
                    analysis.risk_areas = normalized_areas[:8]
                else:
                    analysis.risk_areas = None

                # Main Recommendation
                rec = data.get("recommendation") or data.get("rec") or data.get("final_recommendation")
                if rec:
                    analysis.recommendation = str(rec)[:500]

                # Suggested Actions (the key "Actions" in the spec)
                acts = data.get("suggested_actions") or data.get("suggestedActions") or data.get("actions") or data.get("next_steps")
                if isinstance(acts, list):
                    analysis.suggested_actions = [str(a) for a in acts if a][:6]
                elif isinstance(acts, str):
                    analysis.suggested_actions = [acts]

                # Also populate the Go/No-Go from the same rich response (keeps #2 feature working)
                llm_go = data.get("go_no_go_decision") or data.get("goNoGo") or data.get("decision")
                if llm_go:
                    analysis.go_no_go_decision = str(llm_go).upper().strip()
                llm_reason = data.get("decision_reasoning") or data.get("reasoning") or data.get("reason")
                if llm_reason:
                    analysis.decision_reasoning = str(llm_reason)

            # Populate fields from LLM response (with safe fallbacks)
            # Prefer actual LLM content even if under different keys (e.g. "text", "completion")
            llm_summary = None
            if isinstance(data, dict):
                llm_summary = data.get("summary") or data.get("ai_summary") or data.get("text") or data.get("completion") or data.get("response")
            if not llm_summary and not isinstance(data, dict):
                llm_summary = str(data)  # if LLM returned raw text somehow
            analysis.ai_summary = (
                llm_summary
                or f"This deployment affects {sum(len(v) for v in impacted.values())} components across {len(impacted)} metadata types. Risk level: {analysis.risk_level}."
            )

            recs = None
            if isinstance(data, dict):
                recs = data.get("recommendations") or data.get("ai_recommendations") or data.get("recommendation")
            if isinstance(recs, list):
                analysis.ai_recommendations = [str(r) for r in recs if r][:5]
            elif recs:
                analysis.ai_recommendations = [str(recs)]
            else:
                # fallback only if no LLM recs at all
                analysis.ai_recommendations = [
                    "Run all Apex tests before deployment to catch integration issues",
                    "Deploy during maintenance window due to high impact",
                    "Create a rollback plan for critical components",
                ]

            issues = None
            if isinstance(data, dict):
                issues = data.get("predicted_issues") or data.get("issues") or data.get("predictedIssues")
            if isinstance(issues, list):
                # Normalize a bit for frontend expectations
                normalized = []
                for issue in issues:
                    if isinstance(issue, dict):
                        normalized.append({
                            "severity": issue.get("severity", "medium"),
                            "component": issue.get("component", "Unknown"),
                            "issue_type": issue.get("issue_type", "general"),
                            "description": issue.get("description", str(issue)),
                            "recommendation": issue.get("recommendation", ""),
                            "confidence": float(issue.get("confidence", 0.7)),
                        })
                    else:
                        normalized.append({"severity": "medium", "component": "Unknown", "description": str(issue)})
                analysis.predicted_issues = normalized
            else:
                analysis.predicted_issues = []

            # If LLM did not provide good structured data (e.g. no "summary" key), enhance with exact package contents
            # so the output is still "exact" to the selected retrieval package rather than purely generic.
            generic_summary = f"This deployment affects {sum(len(v) for v in impacted.values())} components across {len(impacted)} metadata types. Risk level: {analysis.risk_level}."
            if (not analysis.ai_summary or analysis.ai_summary == generic_summary or len(analysis.ai_summary.strip()) < 30):
                comp_desc = []
                for t, items in (changed_items or {}).items():
                    sample = ', '.join(items[:3])
                    comp_desc.append(f"{t} ({len(items)}): {sample}")
                pkg_desc = '; '.join(comp_desc[:5])
                analysis.ai_summary = f"Retrieval package from selected metadata retrieval contains changes to: {pkg_desc}. " + generic_summary

            if analysis.ai_recommendations and len(analysis.ai_recommendations) == 3 and "Run all Apex tests" in (analysis.ai_recommendations[0] or ""):
                # still the pure hardcoded fallback list
                first_comp = next(iter((changed_items or {}).keys()), "components")
                analysis.ai_recommendations = [
                    f"Thoroughly test the specific {first_comp} and related flows from this package.",
                    "Deploy outside peak hours and monitor logs for the changed items.",
                    "Review dependencies for the exact classes/objects in the retrieval package."
                ] + analysis.ai_recommendations  # keep some original

            # Ensure Go/No-Go decision is always present (derive from release_score if LLM omitted it)
            if not analysis.go_no_go_decision:
                rs = analysis.release_score or release_score or 50
                if rs >= 75:
                    analysis.go_no_go_decision = "GO"
                    analysis.decision_reasoning = analysis.decision_reasoning or f"Release Score: {rs}. Low risk of failure based on historical success rate, test coverage, complexity, and org health. Safe to deploy."
                elif rs >= 40:
                    analysis.go_no_go_decision = "HOLD"
                    analysis.decision_reasoning = analysis.decision_reasoning or f"Release Score: {rs}. Moderate risk. Hold deployment pending review of AI recommendations and predicted issues."
                else:
                    analysis.go_no_go_decision = "NO-GO"
                    analysis.decision_reasoning = analysis.decision_reasoning or f"Release Score: {rs}. High probability of failure. Do not deploy until risks are mitigated."

            # Safety net for core AI Release Intelligence fields (if LLM gave partial JSON)
            if not analysis.release_readiness:
                analysis.release_readiness = analysis.release_score or release_score or 50
            if not analysis.risk_areas:
                # Derive simple risk areas from current changed + impacted + risk level
                areas = []
                for t, items in (changed_items or {}).items():
                    for name in items[:2]:
                        areas.append({"name": name, "severity": "high" if analysis.risk_level in ("high", "critical") else "medium", "details": f"Changed {t} with detected impacts"})
                for t, items in (impacted or {}).items():
                    for name in items[:1]:
                        areas.append({"name": name, "severity": "medium", "details": "Impacted component"})
                analysis.risk_areas = areas[:5] or [{"name": "General deployment risk", "severity": analysis.risk_level or "medium", "details": "Based on volume and component types"}]
            if not analysis.recommendation:
                rs = analysis.release_readiness or 50
                analysis.recommendation = f"{'Deploy with caution' if rs >= 60 else 'Hold or remediate before deploy'} after reviewing {len(analysis.risk_areas or [])} risk areas."
            if not analysis.suggested_actions:
                rs = analysis.release_readiness or 50
                acts = ["generate_release_plan"]
                if rs >= 75:
                    acts = ["approve", "generate_release_plan"]
                elif rs >= 50:
                    acts = ["hold", "suggest_fixes", "generate_release_plan"]
                else:
                    acts = ["hold", "suggest_fixes", "run_more_tests"]
                analysis.suggested_actions = acts

            analysis.llm_used = True
            await self.db.commit()
            preview = (llm_response or "")[:160].replace("\n", " ")
            logger.info(f"Real LLM insights generated for analysis {analysis.id} using model {getattr(llm_service.settings, 'llm_model', 'default')}. Preview: {preview}...")
            logger.info(f"[LLM] Final ai_summary (first 120 chars): {(analysis.ai_summary or '')[:120]}")
            logger.info(f"[LLM] llm_used persisted as True for {analysis.id}")


        except Exception as e:
            logger.warning(f"Real LLM insights generation failed, using fallback: {e}")
            # Package-aware fallback (no hardcoded generic that ignores the actual retrieval package)
            generic = f"This deployment affects {sum(len(v) for v in impacted.values())} components across {len(impacted)} metadata types. Risk level: {analysis.risk_level}."
            comp_desc = []
            for t, items in (changed_items or {}).items():
                sample = ', '.join(items[:3])
                comp_desc.append(f"{t} ({len(items)}): {sample}")
            pkg_desc = '; '.join(comp_desc[:5])
            analysis.ai_summary = f"Retrieval package from selected metadata retrieval contains changes to: {pkg_desc}. " + generic

            first_type = next(iter((changed_items or {}).keys()), "ApexClass")
            analysis.ai_recommendations = [
                f"Thoroughly test the specific {first_type} and related flows from this exact package.",
                "Deploy outside peak hours and monitor logs for the changed items in the retrieval.",
                "Review dependencies for the exact classes/objects listed in the package."
            ]

            analysis.predicted_issues = [
                {
                    "severity": "high" if (analysis.risk_score or 0) > 50 else "medium",
                    "component": first_type,
                    "issue_type": "general",
                    "description": f"Changes to {first_type} from the retrieval package may cause integration or test issues.",
                    "recommendation": "Review and update tests for the specific components in this package.",
                    "confidence": 0.7,
                }
            ]

            # Fallback Go/No-Go decision based on the pre-calculated release score (historical factors)
            rs = analysis.release_score or release_score or 50
            if rs >= 75:
                analysis.go_no_go_decision = "GO"
                analysis.decision_reasoning = f"Release Score: {rs}. Based on deployment history, test coverage, metadata complexity, incidents and org health factors. Recommended to proceed."
            elif rs >= 40:
                analysis.go_no_go_decision = "HOLD"
                analysis.decision_reasoning = f"Release Score: {rs}. Moderate risk per historical signals. Hold for manual review (see AI recommendations)."
            else:
                analysis.go_no_go_decision = "NO-GO"
                analysis.decision_reasoning = f"Release Score: {rs}. High probability of deployment failure based on past patterns. Do not proceed."

            # Fallback AI Release Intelligence (no LLM) — synthesize from available signals + base calc
            analysis.release_readiness = rs
            # Risk areas from changed + impacted + risk level
            areas = []
            for t, items in (changed_items or {}).items():
                for nm in items[:2]:
                    areas.append({"name": nm, "severity": "high" if (analysis.risk_level in ("high","critical")) else "medium", "details": f"Direct change to {t}"})
            for t, items in (impacted or {}).items():
                for nm in items[:1]:
                    areas.append({"name": nm, "severity": "medium", "details": "Impacted by changes"})
            analysis.risk_areas = areas[:6] or [{"name": "Overall deployment surface", "severity": analysis.risk_level or "medium", "details": "Volume and type of metadata"}]
            analysis.recommendation = f"{'Deploy after review' if rs >= 65 else 'Hold deployment and address risks'} — {len(analysis.risk_areas)} risk areas identified from history and impact."
            if rs >= 75:
                analysis.suggested_actions = ["approve", "generate_release_plan"]

    async def _build_ai_dependency_graph(self, analysis: ImpactAnalysis) -> None:
        """
        Build AI-powered dependency graph with automatic missing dependency detection.
        This is the core of the "AI Dependency Graph + Auto Package Builder" feature.
        """
        from app.application.services.dependency_graph_service import DependencyGraphService
        
        try:
            graph_service = DependencyGraphService(self.db)
            
            # Build comprehensive dependency graph
            graph_result = await graph_service.build_dependency_graph(
                analysis_id=analysis.id,
                components=analysis.changed_items,
                include_missing=True,
                use_ai=True,  # Enable AI-powered dependency discovery
            )
            
            # Store graph data in analysis
            analysis.dependency_graph = graph_result["graph"]
            analysis.missing_dependencies = graph_result["missing_dependencies"]
            analysis.deployment_order = graph_result["deployment_order"]
            analysis.validation_order = graph_result["validation_order"]
            
            # Generate package.xml with all dependencies
            all_components = dict(analysis.changed_items)
            
            # Auto-add critical missing dependencies
            if graph_result["missing_dependencies"]:
                from app.schemas.impact_analysis import MissingDependency
                
                missing_deps = [
                    MissingDependency(**dep) 
                    for dep in graph_result["missing_dependencies"]
                ]
                
                # Auto-add critical dependencies (PermissionSet, CustomMetadata)
                added = await graph_service.auto_add_missing_dependencies(
                    analysis.id, 
                    [d for d in missing_deps if d.severity in ["critical", "high"]]
                )
                
                # Merge added components
                for dep_type, names in added.items():
                    if dep_type in all_components:
                        all_components[dep_type].extend(names)
                    else:
                        all_components[dep_type] = names
                
                # Store metadata about auto-added components
                analysis.package_metadata = {
                    "auto_added": added,
                    "auto_added_count": sum(len(names) for names in added.values()),
                    "total_components": len(graph_result["deployment_order"]),
                }
                analysis.auto_package_generated = True
            
            # Generate package.xml
            package_xml = await graph_service.generate_package_xml(
                analysis.id, all_components, include_dependencies=True
            )
            
            # Update suggested_package with the new package.xml
            if not analysis.suggested_package:
                analysis.suggested_package = {}
            analysis.suggested_package["package_xml"] = package_xml
            analysis.suggested_package["components"] = all_components
            
            await self.db.commit()
            
            logger.info(
                f"Built AI dependency graph for analysis {analysis.id}: "
                f"{len(graph_result['graph']['nodes'])} nodes, "
                f"{len(graph_result['graph']['edges'])} edges, "
                f"{len(graph_result['missing_dependencies'])} missing deps"
            )
            
        except Exception as e:
            logger.error(f"Failed to build AI dependency graph: {e}")
            # Don't fail the entire analysis if graph building fails
            analysis.dependency_graph = None
            analysis.missing_dependencies = []
            analysis.deployment_order = []
            analysis.validation_order = []
            # recovery handled by caller (run_analysis); do not commit partial here

    async def _build_deployment_package(self, analysis: ImpactAnalysis) -> None:
        """Build deployment package with all required components."""
        changed_items = analysis.changed_items
        impacted = analysis.impacted_components or {}

        # Combine changed and impacted items
        all_components = {}
        for comp_type, items in changed_items.items():
            all_components[comp_type] = list(set(items))

        for comp_type, items in impacted.items():
            if comp_type not in all_components:
                all_components[comp_type] = []
            all_components[comp_type].extend(items)
            all_components[comp_type] = list(set(all_components[comp_type]))

        # Generate package.xml
        package_xml = self._generate_package_xml(all_components)

        # Suggest test classes
        test_classes = []
        if "ApexClass" in all_components:
            test_classes = [f"{cls}Test" for cls in all_components["ApexClass"]]

        analysis.suggested_package = {
            "package_xml": package_xml,
            "components": all_components,
            "test_classes": test_classes,
            "deployment_order": list(all_components.keys()),
            "estimated_duration_minutes": len(all_components) * 2,
        }
        await self.db.commit()

    def _generate_package_xml(self, components: dict[str, list[str]]) -> str:
        """Generate package.xml content."""
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Package xmlns="http://soap.sforce.com/2006/04/metadata">']

        for comp_type, members in sorted(components.items()):
            xml_parts.append(f"    <types>")
            for member in sorted(set(members)):
                xml_parts.append(f"        <members>{member}</members>")
            xml_parts.append(f"        <name>{comp_type}</name>")
            xml_parts.append(f"    </types>")

        xml_parts.append("    <version>62.0</version>")
        xml_parts.append("</Package>")

        return "\n".join(xml_parts)

    async def get_dependency_graph(self, analysis_id: UUID) -> DependencyGraph:
        """Build dependency graph for visualization."""
        result = await self.db.execute(
            select(ImpactAnalysis)
            .where(ImpactAnalysis.id == analysis_id)
            .options(selectinload(ImpactAnalysis.dependencies))
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        nodes = []
        edges = []
        node_ids = set()

        # Add changed items as nodes
        for comp_type, items in analysis.changed_items.items():
            for item in items:
                node_id = f"{comp_type}:{item}"
                if node_id not in node_ids:
                    nodes.append(
                        DependencyNode(
                            id=node_id,
                            type=comp_type,
                            name=item,
                            is_changed=True,
                            risk_level=analysis.risk_level,
                        )
                    )
                    node_ids.add(node_id)

        # Add dependencies as nodes and edges
        for dep in analysis.dependencies:
            target_id = f"{dep.target_type}:{dep.target_name}"
            if target_id not in node_ids:
                nodes.append(
                    DependencyNode(
                        id=target_id,
                        type=dep.target_type,
                        name=dep.target_name,
                        is_impacted=True,
                    )
                )
                node_ids.add(target_id)

            edges.append(
                DependencyEdge(
                    source=f"{dep.source_type}:{dep.source_name}",
                    target=target_id,
                    dependency_type=dep.dependency_type,
                    confidence=dep.confidence,
                )
            )

        return DependencyGraph(
            nodes=nodes,
            edges=edges,
            stats={
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "changed_count": len([n for n in nodes if n.is_changed]),
                "impacted_count": len([n for n in nodes if n.is_impacted]),
            },
        )

    async def list_analyses(
        self, org_id: UUID | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[ImpactAnalysis], int]:
        """List impact analyses with pagination."""
        query = select(ImpactAnalysis)
        if org_id:
            query = query.where(ImpactAnalysis.org_id == org_id)

        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Get paginated results
        query = query.order_by(ImpactAnalysis.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        analyses = result.scalars().all()

        return list(analyses), total

    async def get_analysis(self, analysis_id: UUID) -> ImpactAnalysis | None:
        """Get a single impact analysis with dependencies."""
        result = await self.db.execute(
            select(ImpactAnalysis)
            .where(ImpactAnalysis.id == analysis_id)
            .options(selectinload(ImpactAnalysis.dependencies))
        )
        return result.scalar_one_or_none()

# Made with Bob
