from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.application.services.llm_agent_service import LLMAgentService
from app.infrastructure.di import get_artifact_store


class PMDAnalysisService:
    """Lightweight PMD-style analysis with IBM guidance grounding and LLM remediation."""

    GUIDANCE_PATH = Path("docs/features/SALESFORCE_PMD_LLM_GUIDANCE.md")
    VECTOR_CACHE_PATH = Path("backend/.pmd_guidance_index.json")

    def __init__(self, db):
        self.db = db
        self.llm_service = LLMAgentService(db)

    def _load_guidance(self) -> str:
        if self.GUIDANCE_PATH.exists():
            return self.GUIDANCE_PATH.read_text(encoding="utf-8")
        return ""

    def _chunk_guidance(self, text: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        current_heading = "General"
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("#"):
                if current_lines:
                    chunks.append(
                        {
                            "heading": current_heading,
                            "text": "\n".join(current_lines).strip(),
                            "tokens": self._tokenize("\n".join(current_lines)),
                        }
                    )
                    current_lines = []
                current_heading = line.lstrip("#").strip()
            else:
                current_lines.append(line)
        if current_lines:
            chunks.append(
                {
                    "heading": current_heading,
                    "text": "\n".join(current_lines).strip(),
                    "tokens": self._tokenize("\n".join(current_lines)),
                }
            )
        return chunks

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text.lower())

    def _ensure_vector_cache(self) -> list[dict[str, Any]]:
        guidance = self._load_guidance()
        chunks = self._chunk_guidance(guidance)
        payload = {"chunks": chunks}
        self.VECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.VECTOR_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return chunks

    def _retrieve_guidance(self, rule_name: str, severity: str, source_snippet: str) -> list[dict[str, Any]]:
        chunks = self._ensure_vector_cache()
        query_tokens = set(self._tokenize(f"{rule_name} {severity} {source_snippet}"))
        scored: list[tuple[int, dict[str, Any]]] = []
        for chunk in chunks:
            overlap = len(query_tokens.intersection(set(chunk.get("tokens", []))))
            if overlap:
                scored.append((overlap, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:3]]

    def _scan_file_for_findings(self, file_path: Path) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return findings

        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            lowered = line.lower()
            if "select " in lowered and " for " not in lowered and idx < len(lines):
                if idx + 1 <= len(lines) and ("for (" in lines[idx].lower() or "for(" in lines[idx].lower()):
                    findings.append(
                        {
                            "rule": "AvoidSoqlInLoops",
                            "severity": "high",
                            "file_path": str(file_path).replace("\\", "/"),
                            "line": idx,
                            "message": "Potential SOQL usage near loop structure; review for bulkification.",
                            "snippet": "\n".join(lines[max(0, idx - 2): min(len(lines), idx + 2)]),
                        }
                    )
            if "database.query(" in lowered or "database.countquery(" in lowered:
                findings.append(
                    {
                        "rule": "ApexSOQLInjection",
                        "severity": "high",
                        "file_path": str(file_path).replace("\\", "/"),
                        "line": idx,
                        "message": "Dynamic SOQL detected; verify bind-variable safety.",
                        "snippet": "\n".join(lines[max(0, idx - 2): min(len(lines), idx + 2)]),
                    }
                )
            if "insert " in lowered or "update " in lowered or "delete " in lowered:
                if idx + 1 <= len(lines) and ("for (" in lines[idx].lower() or "for(" in lines[idx].lower()):
                    findings.append(
                        {
                            "rule": "AvoidDmlStatementsInLoops",
                            "severity": "high",
                            "file_path": str(file_path).replace("\\", "/"),
                            "line": idx,
                            "message": "Potential DML usage near loop structure; review for bulk-safe batching.",
                            "snippet": "\n".join(lines[max(0, idx - 2): min(len(lines), idx + 2)]),
                        }
                    )
            if "catch (exception" in lowered:
                findings.append(
                    {
                        "rule": "ApexGenericExceptionCatch",
                        "severity": "medium",
                        "file_path": str(file_path).replace("\\", "/"),
                        "line": idx,
                        "message": "Generic exception catch detected; prefer narrower exception handling.",
                        "snippet": "\n".join(lines[max(0, idx - 2): min(len(lines), idx + 2)]),
                    }
                )
        return findings

    async def _generate_llm_fix(self, finding: dict[str, Any], guidance_chunks: list[dict[str, Any]]) -> str:
        guidance_text = "\n\n".join(
            f"[{chunk.get('heading', 'Guidance')}]\n{chunk.get('text', '')[:1200]}" for chunk in guidance_chunks
        )
        prompt = f"""
You are an IBM Salesforce code quality reviewer.
Generate an exact remediation suggestion for this PMD finding.

Finding:
- Rule: {finding.get("rule")}
- Severity: {finding.get("severity")}
- File: {finding.get("file_path")}
- Line: {finding.get("line")}
- Message: {finding.get("message")}

Source snippet:
{finding.get("snippet", "")}

Grounding guidance:
{guidance_text}

Return a concise business-safe remediation with:
1. exact issue explanation
2. exact fix direction for this file/class
3. deployment risk impact
"""
        try:
            response = await self.llm_service._call_llm(prompt)
            return str(response).strip()[:3000]
        except Exception:
            return (
                f"Review {finding.get('file_path')} line {finding.get('line')} for rule {finding.get('rule')}. "
                f"Apply IBM guidance to remediate the flagged pattern with the smallest safe code change."
            )

    async def analyze_directory(self, source_root: str, deployment_id: str | None = None) -> dict[str, Any]:
        root = Path(source_root)
        if not root.exists():
            return {
                "status": "failed",
                "summary": "PMD analysis source directory not found.",
                "findings": [],
                "totals": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
            }

        candidate_files = [
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".cls", ".trigger", ".apex"}
        ]

        findings: list[dict[str, Any]] = []
        for file_path in candidate_files:
            findings.extend(self._scan_file_for_findings(file_path))

        for finding in findings:
            guidance_chunks = self._retrieve_guidance(
                finding.get("rule", ""),
                finding.get("severity", ""),
                finding.get("snippet", ""),
            )
            finding["guidance_context"] = [chunk.get("heading") for chunk in guidance_chunks]
            finding["llm_fix_suggestion"] = await self._generate_llm_fix(finding, guidance_chunks)

        totals = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": len(findings)}
        for finding in findings:
            sev = str(finding.get("severity", "low")).lower()
            if sev in totals:
                totals[sev] += 1

        summary = (
            f"PMD-style review completed with {totals['total']} finding(s): "
            f"{totals['high']} high, {totals['medium']} medium, {totals['low']} low."
        )

        result = {
            "status": "success",
            "summary": summary,
            "findings": findings,
            "totals": totals,
            "source_root": str(root).replace("\\", "/"),
            "deployment_id": deployment_id,
            "knowledge_base": str(self.GUIDANCE_PATH).replace("\\", "/"),
            "vector_cache": str(self.VECTOR_CACHE_PATH).replace("\\", "/"),
        }

        if deployment_id:
            artifact_store = get_artifact_store()
            key = f"deployments/{deployment_id}/pmd-analysis.json"
            await artifact_store.save(key, json.dumps(result, indent=2).encode("utf-8"), "application/json")
            result["artifact_key"] = key

        return result

# Made with Bob
