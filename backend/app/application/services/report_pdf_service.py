"""IBM-only PDF report generation for business-ready Salesforce analysis outputs."""

from __future__ import annotations

import io
from collections.abc import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from app.infrastructure.db.models import ImpactAnalysis


class ReportPDFService:
    """Builds IBM-formatted printable PDF reports from persisted impact analysis data."""

    IBM_BLUE = colors.HexColor("#0F62FE")
    IBM_TEXT = colors.HexColor("#161616")
    IBM_MUTED = colors.HexColor("#525252")
    IBM_BORDER = colors.HexColor("#C6C6C6")
    IBM_SURFACE = colors.HexColor("#F4F4F4")
    IBM_HEADER = colors.HexColor("#E8F0FE")

    def _styles(self):
        styles = getSampleStyleSheet()
        styles["Title"].fontName = "Helvetica-Bold"
        styles["Title"].fontSize = 20
        styles["Title"].leading = 24
        styles["Title"].textColor = self.IBM_TEXT

        styles.add(
            ParagraphStyle(
                name="IBMReportLabel",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=11,
                textColor=self.IBM_BLUE,
                spaceAfter=4,
                uppercase=True,
            )
        )
        styles.add(
            ParagraphStyle(
                name="IBMSubtitle",
                parent=styles["BodyText"],
                fontSize=10,
                leading=14,
                textColor=self.IBM_MUTED,
                spaceAfter=8,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionTitle",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=16,
                textColor=self.IBM_TEXT,
                spaceBefore=10,
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="BodySmall",
                parent=styles["BodyText"],
                fontSize=9,
                leading=13,
                textColor=self.IBM_TEXT,
            )
        )
        styles.add(
            ParagraphStyle(
                name="ExecutiveSummary",
                parent=styles["BodyText"],
                fontSize=10,
                leading=14,
                textColor=self.IBM_TEXT,
                backColor=self.IBM_SURFACE,
                borderPadding=8,
                borderColor=self.IBM_BORDER,
                borderWidth=0.5,
                borderRadius=2,
                spaceAfter=8,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CodeBlock",
                parent=styles["Code"],
                fontName="Courier",
                fontSize=7,
                leading=9,
                textColor=self.IBM_TEXT,
                backColor=self.IBM_SURFACE,
                borderPadding=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="FooterNote",
                parent=styles["BodyText"],
                fontSize=8,
                leading=10,
                textColor=self.IBM_MUTED,
                alignment=1,
            )
        )
        return styles

    def _table(self, rows: list[list[str]]) -> Table:
        table = Table(rows, colWidths=[170, 350])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, self.IBM_BORDER),
                    ("BACKGROUND", (0, 0), (-1, 0), self.IBM_HEADER),
                    ("TEXTCOLOR", (0, 0), (-1, 0), self.IBM_TEXT),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _bullet_block(self, title: str, items: Iterable[str], styles) -> list:
        flow = [Paragraph(title, styles["SectionTitle"])]
        values = [i for i in items if i]
        if not values:
            flow.append(Paragraph("No material data available for this section.", styles["BodySmall"]))
            return flow
        for item in values:
            flow.append(Paragraph(f"• {item}", styles["BodySmall"]))
        return flow

    def _metadata_table(self, report_type: str, analysis: ImpactAnalysis | object) -> Table:
        analysis_id = getattr(analysis, "id", "n/a")
        created_at = getattr(analysis, "created_at", "n/a")
        rows = [
            ["Report Attribute", "Details"],
            ["Organization", "IBM"],
            ["Report Type", report_type],
            ["Analysis Identifier", str(analysis_id)],
            ["Generated On", str(created_at)],
            ["Prepared For", "IBM internal business reporting"],
            ["Confidentiality", "IBM Confidential – Internal Use Only"],
        ]
        return self._table(rows)

    def _component_scope_summary(self, analysis: ImpactAnalysis) -> str:
        changed_items = analysis.changed_items or {}
        total_components = sum(len(items) for items in changed_items.values())
        total_types = len(changed_items)
        if not changed_items:
            return "No changed metadata components were provided for this assessment."
        top_types = sorted(changed_items.items(), key=lambda item: len(item[1]), reverse=True)[:3]
        top_desc = ", ".join(f"{meta_type} ({len(items)})" for meta_type, items in top_types)
        return (
            f"The current assessment covers {total_components} changed component(s) across "
            f"{total_types} metadata type(s). Primary concentration areas are {top_desc}."
        )

    def _release_executive_summary(self, analysis: ImpactAnalysis) -> str:
        readiness = analysis.release_readiness if analysis.release_readiness is not None else "n/a"
        decision = analysis.go_no_go_decision or "undetermined"
        risk_level = analysis.risk_level or "unknown"
        recommendation = analysis.recommendation or "No formal recommendation was generated."
        llm_summary = (analysis.ai_summary or "").strip()
        reasoning = (analysis.decision_reasoning or "").strip()

        summary_parts = [
            f"IBM assessment indicates release readiness at {readiness} with an overall decision posture of {decision}.",
            f"Current delivery risk is classified as {risk_level}.",
            self._component_scope_summary(analysis),
        ]

        if llm_summary:
            summary_parts.append(llm_summary)
        else:
            summary_parts.append(recommendation)

        if reasoning:
            summary_parts.append(f"Decision rationale: {reasoning}")

        return " ".join(part for part in summary_parts if part)

    def _dependency_executive_summary(self, analysis: ImpactAnalysis, stats: dict) -> str:
        total_nodes = stats.get("total_nodes", 0)
        total_edges = stats.get("total_edges", 0)
        changed_components = stats.get("changed_components", 0)
        impacted_components = stats.get("impacted_components", 0)
        missing_count = len(analysis.missing_dependencies or [])
        auto_package = "enabled" if analysis.auto_package_generated else "not generated"

        summary_parts = [
            "IBM dependency analysis has evaluated deployment sequencing and package completeness for the requested Salesforce scope.",
            f"The dependency graph contains {total_nodes} node(s) and {total_edges} relationship(s), covering {changed_components} changed component(s) and {impacted_components} impacted component(s).",
            f"Missing dependency count is {missing_count}, and automated package generation was {auto_package}.",
            self._component_scope_summary(analysis),
        ]

        if analysis.ai_summary:
            summary_parts.append(str(analysis.ai_summary).strip())

        return " ".join(part for part in summary_parts if part)

    def _recommendation_narrative(self, analysis: ImpactAnalysis) -> str:
        recommendations = [str(item).strip() for item in (analysis.ai_recommendations or []) if str(item).strip()]
        actions = [str(item).strip() for item in (analysis.suggested_actions or []) if str(item).strip()]
        recommendation = (analysis.recommendation or "").strip()

        parts = []
        if recommendation:
            parts.append(recommendation)
        if recommendations:
            parts.append("Priority recommendations include: " + "; ".join(recommendations[:4]) + ".")
        if actions:
            parts.append("Expected next actions are: " + ", ".join(actions[:5]) + ".")
        if not parts:
            parts.append("No explicit recommendation set was available; IBM reviewers should validate deployment readiness before approval.")
        return " ".join(parts)

    def _issue_narrative(self, analysis: ImpactAnalysis) -> str:
        issues = analysis.predicted_issues or []
        if not issues:
            return "No predicted delivery issues were generated for this assessment."
        top_issues = []
        for issue in issues[:3]:
            if isinstance(issue, dict):
                severity = str(issue.get("severity", "medium")).upper()
                component = str(issue.get("component", "Unknown"))
                description = str(issue.get("description", "")).strip()
                top_issues.append(f"{severity} risk on {component}: {description}")
        if not top_issues:
            return "Predicted issues were present but did not contain sufficient structured detail for narrative reporting."
        return "Key predicted delivery issues include " + "; ".join(top_issues) + "."

    def _draw_page_frame(self, canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(self.IBM_BLUE)
        canvas.rect(18 * mm, height - 18 * mm, width - 36 * mm, 4, stroke=0, fill=1)
        canvas.setStrokeColor(self.IBM_BORDER)
        canvas.line(18 * mm, 16 * mm, width - 18 * mm, 16 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(self.IBM_MUTED)
        canvas.drawString(18 * mm, 10 * mm, "IBM Confidential – Internal Use Only")
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _build_pdf(self, title: str, subtitle: str, sections: list, analysis: ImpactAnalysis | object, report_type: str) -> bytes:
        styles = self._styles()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            author="IBM",
            subject=subtitle,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=22 * mm,
            bottomMargin=22 * mm,
        )

        story = [
            Paragraph("IBM BUSINESS REPORT", styles["IBMReportLabel"]),
            Paragraph(title, styles["Title"]),
            Paragraph(subtitle, styles["IBMSubtitle"]),
            self._metadata_table(report_type, analysis),
            Spacer(1, 12),
        ]
        story.extend(sections)
        story.extend(
            [
                Spacer(1, 14),
                Paragraph("This document is intended solely for IBM internal business review and decision support.", styles["FooterNote"]),
            ]
        )
        doc.build(story, onFirstPage=self._draw_page_frame, onLaterPages=self._draw_page_frame)
        return buffer.getvalue()

    def generate_release_intelligence_pdf(self, analysis: ImpactAnalysis) -> bytes:
        styles = self._styles()

        overview_rows = [
            ["Field", "Value"],
            ["Analysis Status", str(analysis.status or "n/a")],
            ["Assessment Type", str(analysis.analysis_type or "n/a")],
            ["Release Readiness", str(analysis.release_readiness if analysis.release_readiness is not None else "n/a")],
            ["Risk Score", str(analysis.risk_score if analysis.risk_score is not None else "n/a")],
            ["Risk Level", str(analysis.risk_level or "n/a")],
            ["Decision Recommendation", str(analysis.go_no_go_decision or "n/a")],
            ["Model Reference", "LLM-generated narrative" if analysis.llm_used else "Deterministic fallback narrative"],
            ["Created At", str(analysis.created_at)],
        ]

        changed_summary = []
        for mtype, members in (analysis.changed_items or {}).items():
            changed_summary.append(f"{mtype}: {len(members)} component(s) in scope")

        risk_area_lines = []
        for area in (analysis.risk_areas or []):
            name = area.get("name", "Unnamed")
            severity = area.get("severity", "unknown")
            details = area.get("details", "")
            risk_area_lines.append(f"{name} [{severity}] - {details}")

        predicted_issue_lines = []
        for issue in (analysis.predicted_issues or []):
            predicted_issue_lines.append(
                f"{issue.get('severity', 'unknown').upper()}: {issue.get('component', 'n/a')} - {issue.get('description', '')}"
            )

        sections = [
            Paragraph("Executive Overview", styles["SectionTitle"]),
            self._table(overview_rows),
            Spacer(1, 8),
            Paragraph("Executive Summary", styles["SectionTitle"]),
            Paragraph(self._release_executive_summary(analysis), styles["ExecutiveSummary"]),
            Spacer(1, 8),
            Paragraph("Recommendation Narrative", styles["SectionTitle"]),
            Paragraph(self._recommendation_narrative(analysis), styles["BodySmall"]),
            Spacer(1, 8),
            Paragraph("Issue Outlook", styles["SectionTitle"]),
            Paragraph(self._issue_narrative(analysis), styles["BodySmall"]),
            Spacer(1, 8),
            *self._bullet_block("Metadata Scope in Review", changed_summary, styles),
            Spacer(1, 8),
            *self._bullet_block("Primary Risk Areas", risk_area_lines, styles),
            Spacer(1, 8),
            *self._bullet_block("IBM Recommendations", [str(x) for x in (analysis.ai_recommendations or [])], styles),
            Spacer(1, 8),
            *self._bullet_block("Suggested Business Actions", [str(x) for x in (analysis.suggested_actions or [])], styles),
            Spacer(1, 8),
            *self._bullet_block("Predicted Delivery Issues", predicted_issue_lines, styles),
        ]

        if analysis.git_diff:
            sections.extend(
                [
                    Spacer(1, 8),
                    Paragraph("Technical Change Context", styles["SectionTitle"]),
                    Preformatted(str(analysis.git_diff)[:8000], styles["CodeBlock"]),
                ]
            )

        return self._build_pdf(
            "IBM Salesforce Release Readiness Report",
            "Business assessment of Salesforce deployment readiness for IBM stakeholders",
            sections,
            analysis,
            "Release Readiness Assessment",
        )

    def generate_dependency_graph_pdf(self, analysis: ImpactAnalysis) -> bytes:
        styles = self._styles()
        graph = analysis.dependency_graph or {}
        stats = graph.get("stats", {}) if isinstance(graph, dict) else {}

        overview_rows = [
            ["Field", "Value"],
            ["Analysis Status", str(analysis.status or "n/a")],
            ["Total Nodes", str(stats.get("total_nodes", 0))],
            ["Total Edges", str(stats.get("total_edges", 0))],
            ["Changed Components", str(stats.get("changed_components", 0))],
            ["Impacted Components", str(stats.get("impacted_components", 0))],
            ["Missing Dependencies", str(len(analysis.missing_dependencies or []))],
            ["Auto Package Generated", str(analysis.auto_package_generated or False)],
            ["Created At", str(analysis.created_at)],
        ]

        missing_lines = []
        for dep in (analysis.missing_dependencies or []):
            missing_lines.append(
                f"{dep.get('type', 'Unknown')}:{dep.get('name', 'n/a')} [{dep.get('severity', 'unknown')}] - {dep.get('reason', '')}"
            )

        deployment_order = [str(x) for x in (analysis.deployment_order or [])]
        validation_order = [str(x) for x in (analysis.validation_order or [])]

        package_xml = ""
        if analysis.suggested_package and isinstance(analysis.suggested_package, dict):
            package_xml = str(analysis.suggested_package.get("package_xml") or "")

        sections = [
            Paragraph("Dependency Overview", styles["SectionTitle"]),
            self._table(overview_rows),
            Spacer(1, 8),
            Paragraph("Executive Summary", styles["SectionTitle"]),
            Paragraph(self._dependency_executive_summary(analysis, stats), styles["ExecutiveSummary"]),
            Spacer(1, 8),
            Paragraph("Recommendation Narrative", styles["SectionTitle"]),
            Paragraph(self._recommendation_narrative(analysis), styles["BodySmall"]),
            Spacer(1, 8),
            *self._bullet_block("Recommended Deployment Order", deployment_order, styles),
            Spacer(1, 8),
            *self._bullet_block("Recommended Validation Order", validation_order, styles),
            Spacer(1, 8),
            *self._bullet_block("Missing Dependencies Requiring Attention", missing_lines, styles),
        ]

        auto_added = None
        if analysis.package_metadata and isinstance(analysis.package_metadata, dict):
            auto_added = analysis.package_metadata.get("auto_added")

        auto_added_lines: list[str] = []
        if isinstance(auto_added, dict):
            for dep_type, names in auto_added.items():
                auto_added_lines.append(f"{dep_type}: {', '.join([str(n) for n in names])}")
        elif isinstance(auto_added, list):
            for item in auto_added:
                if isinstance(item, dict):
                    auto_added_lines.append(
                        f"{item.get('type', 'Unknown')}: {', '.join([str(n) for n in item.get('names', [])])}"
                    )

        sections.extend(
            [
                Spacer(1, 8),
                *self._bullet_block("Auto-added Components", auto_added_lines, styles),
                Spacer(1, 8),
                Paragraph("Generated package.xml", styles["SectionTitle"]),
                Preformatted((package_xml or "No package.xml generated.")[:12000], styles["CodeBlock"]),
            ]
        )

        return self._build_pdf(
            "IBM Salesforce Dependency and Package Report",
            "Business-ready dependency and package analysis for IBM Salesforce delivery teams",
            sections,
            analysis,
            "Dependency and Package Assessment",
        )

    def generate_pmd_analysis_pdf(self, deployment_id: str, pmd_result: dict) -> bytes:
        styles = self._styles()

        totals = pmd_result.get("totals", {}) if isinstance(pmd_result, dict) else {}
        findings = pmd_result.get("findings", []) if isinstance(pmd_result, dict) else []
        artifact_key = pmd_result.get("artifact_key", "n/a") if isinstance(pmd_result, dict) else "n/a"

        overview_rows = [
            ["Field", "Value"],
            ["Deployment Identifier", str(deployment_id)],
            ["Analysis Status", str(pmd_result.get("status", "n/a"))],
            ["Total Findings", str(totals.get("total", 0))],
            ["High Severity", str(totals.get("high", 0))],
            ["Medium Severity", str(totals.get("medium", 0))],
            ["Low Severity", str(totals.get("low", 0))],
            ["Knowledge Base", str(pmd_result.get("knowledge_base", "n/a"))],
            ["Artifact Key", str(artifact_key)],
        ]

        finding_lines: list[str] = []
        remediation_lines: list[str] = []
        for finding in findings[:12]:
            if not isinstance(finding, dict):
                continue
            finding_lines.append(
                f"{finding.get('severity', 'unknown').upper()} | {finding.get('rule', 'UnknownRule')} | "
                f"{finding.get('file_path', 'n/a')}:{finding.get('line', 'n/a')} - {finding.get('message', '')}"
            )
            remediation_lines.append(
                f"{finding.get('rule', 'UnknownRule')} - {str(finding.get('llm_fix_suggestion', 'No remediation generated.'))[:700]}"
            )

        sections = [
            Paragraph("PMD Review Overview", styles["SectionTitle"]),
            self._table(overview_rows),
            Spacer(1, 8),
            Paragraph("Executive Summary", styles["SectionTitle"]),
            Paragraph(
                str(pmd_result.get("summary", "No PMD summary available.")),
                styles["ExecutiveSummary"],
            ),
            Spacer(1, 8),
            *self._bullet_block("Detected Findings", finding_lines, styles),
            Spacer(1, 8),
            *self._bullet_block("LLM Remediation Guidance", remediation_lines, styles),
        ]

        class _PMDAnalysisProxy:
            id = deployment_id
            created_at = "Generated during deployment pre-check"

        return self._build_pdf(
            "IBM Salesforce PMD Analysis Report",
            "Business-ready PMD quality and remediation assessment for IBM Salesforce delivery teams",
            sections,
            _PMDAnalysisProxy(),
            "PMD Quality Assessment",
        )
