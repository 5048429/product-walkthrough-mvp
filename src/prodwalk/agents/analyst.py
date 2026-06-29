from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any
from urllib.parse import urlparse

from ..models import (
    CompetitiveInsight,
    Finding,
    ProductAnalysis,
    WalkthroughResult,
    normalize_report_language,
    slugify,
)


DESTRUCTIVE_KEYWORDS = (
    "archive",
    "delete",
    "disable",
    "edit",
    "export",
    "generate",
    "pay",
    "payout",
    "refund",
    "remove",
    "revoke",
    "save",
    "submit",
    "transfer",
    "void",
)


class ProductAnalyst:
    def analyze(self, results: list[WalkthroughResult], language: str = "en") -> list[ProductAnalysis]:
        language = normalize_report_language(language)
        by_product: dict[str, list[WalkthroughResult]] = defaultdict(list)
        for result in results:
            by_product[result.product].append(result)

        analyses: list[ProductAnalysis] = []
        for product, product_results in by_product.items():
            findings: list[Finding] = []
            for result in product_results:
                findings.extend(self._findings_for_result(result, language))

            avg_completion = self._avg(result.metrics.get("completion_score", 0) for result in product_results)
            total_blockers = sum(int(result.metrics.get("blocker_count", 0)) for result in product_results)
            total_friction = sum(int(result.metrics.get("friction_count", 0)) for result in product_results)
            structured_findings = [finding for finding in findings if not finding.id.endswith("-positive")]
            product_issues = [finding for finding in structured_findings if finding.issue_type == "product"]
            coverage_gaps = [finding for finding in structured_findings if finding.issue_type == "coverage"]
            reliability_issues = [
                finding for finding in structured_findings if finding.issue_type == "system_reliability"
            ]
            checklist_stats = self._checklist_stats(product_results)

            if language == "zh":
                summary = (
                    f"{product} 共完成 {len(product_results)} 个场景，发现 "
                    f"{len(product_issues)} 个产品问题、{len(coverage_gaps)} 个覆盖缺口、"
                    f"{len(reliability_issues)} 个系统可靠性风险。"
                )
            else:
                summary = (
                    f"{product} completed {len(product_results)} scenarios with "
                    f"{len(product_issues)} product issues, {len(coverage_gaps)} coverage gaps, "
                    f"and {len(reliability_issues)} system reliability risks."
                )

            analyses.append(
                ProductAnalysis(
                    product=product,
                    summary=summary,
                    findings=findings,
                    metrics={
                        "scenario_count": len(product_results),
                        "avg_completion_score": round(avg_completion, 2),
                        "total_blockers": total_blockers,
                        "total_friction": total_friction,
                        "structured_findings": len(structured_findings),
                        "product_issue_count": len(product_issues),
                        "coverage_gap_count": len(coverage_gaps),
                        "system_reliability_issue_count": len(reliability_issues),
                        **checklist_stats,
                    },
                )
            )
        return analyses

    def _findings_for_result(self, result: WalkthroughResult, language: str) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._strict_issue_findings_for_result(result, language))
        findings.extend(self._legacy_summary_findings_for_result(result, language))
        findings.extend(self._page_evidence_findings_for_result(result, language))
        findings.extend(self._step_status_findings_for_result(result, language))
        findings = self._dedupe_findings(findings)

        if not findings and result.evidence:
            claim = (
                "该配置旅程采集到了基础证据，未发现明确阻塞点。"
                if language == "zh"
                else "The configured journey produced baseline evidence without obvious blockers."
            )
            recommendation = (
                "发布决策前仍建议用真实浏览器会话复跑该场景，并补充人工标注的验收样本。"
                if language == "zh"
                else "Replay this scenario with a real browser session and a labeled acceptance sample before release decisions."
            )
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-positive",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity="low",
                    theme="Baseline pass",
                    claim=claim,
                    evidence_ids=[result.evidence[0].id],
                    recommendation=recommendation,
                    confidence=0.6,
                    issue_type="positive",
                    priority="P4",
                    page=result.evidence[0].url,
                    current_behavior=claim,
                    expected_behavior=recommendation,
                    repro_steps=self._scenario_repro_steps(result),
                    acceptance_criteria=[recommendation],
                    screenshot_refs=self._screenshot_refs_for_item(result.evidence[0]),
                    source="baseline",
                    confidence_reason="No blocker, friction, strict issue, or page-evidence detector fired.",
                )
            )
        return findings

    def _strict_issue_findings_for_result(self, result: WalkthroughResult, language: str) -> list[Finding]:
        payload, fallback_evidence_id = self._final_summary_payload(result)
        if not payload:
            return []

        raw_issues = (
            payload.get("issues")
            or payload.get("product_issues")
            or payload.get("findings")
            or payload.get("pm_issues")
        )
        issues = raw_issues if isinstance(raw_issues, list) else []
        findings: list[Finding] = []
        for index, raw_issue in enumerate(issues, start=1):
            issue = self._issue_dict(raw_issue)
            if not issue:
                continue
            claim = self._clean_text(
                str(
                    issue.get("claim")
                    or issue.get("title")
                    or issue.get("summary")
                    or issue.get("actual")
                    or issue.get("current_behavior")
                    or ""
                )
            )
            if not claim or self._is_non_issue(claim):
                continue

            source = str(issue.get("source") or "strict_summary")
            issue_type = self._issue_type(issue, default="product")
            severity = self._severity_value(issue.get("severity")) or self._classify_issue(claim, source)[0]
            theme = self._clean_text(str(issue.get("theme") or issue.get("area") or "")) or self._classify_issue(claim, source)[1]
            recommendation = self._clean_text(
                str(issue.get("recommendation") or issue.get("suggestion") or "")
            ) or self._fallback_recommendation(theme, source, language)
            evidence_ids = self._evidence_ids(issue.get("evidence_ids") or issue.get("evidence"), fallback_evidence_id)

            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-issue-{index}",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity=severity,
                    theme=theme,
                    claim=claim,
                    evidence_ids=evidence_ids,
                    recommendation=recommendation,
                    confidence=self._confidence_value(issue.get("confidence"), default=0.84),
                    issue_type=issue_type,
                    priority=self._priority_value(issue.get("priority"), severity),
                    page=self._clean_text(str(issue.get("page") or issue.get("url") or "")),
                    current_behavior=self._clean_text(
                        str(issue.get("current_behavior") or issue.get("actual") or claim)
                    ),
                    expected_behavior=self._clean_text(
                        str(issue.get("expected_behavior") or issue.get("expected") or self._expected_behavior(theme, language))
                    ),
                    repro_steps=self._text_list(issue.get("repro_steps") or issue.get("steps"))
                    or self._scenario_repro_steps(result),
                    acceptance_criteria=self._text_list(issue.get("acceptance_criteria"))
                    or self._acceptance_criteria(theme, recommendation, language),
                    screenshot_refs=self._text_list(issue.get("screenshot_refs") or issue.get("screenshots")),
                    source=source,
                    confidence_reason=self._clean_text(
                        str(issue.get("confidence_reason") or "Structured browser summary supplied this issue.")
                    ),
                )
            )
        return findings

    def _legacy_summary_findings_for_result(self, result: WalkthroughResult, language: str) -> list[Finding]:
        payload, evidence_id = self._final_summary_payload(result)
        if not payload or not evidence_id:
            return []

        recommendations = self._as_text_list(payload.get("top_recommendations"))
        raw_items: list[tuple[str, str]] = []
        for item in self._as_text_list(payload.get("blockers") or payload.get("blocked_sections")):
            raw_items.append(("blocker", item))
        for item in self._as_text_list(payload.get("friction_points")):
            raw_items.append(("friction", item))

        findings: list[Finding] = []
        for index, (source, claim) in enumerate(raw_items, start=1):
            claim = self._clean_text(claim)
            if not claim or self._is_non_issue(claim):
                continue
            severity, theme = self._classify_issue(claim, source)
            recommendation = self._best_recommendation(
                claim,
                recommendations,
                fallback=self._fallback_recommendation(theme, source, language),
                theme=theme,
                minimum_score=2,
            )
            evidence_item = self._evidence_by_id(result, evidence_id)
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-summary-{index}",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity=severity,
                    theme=theme,
                    claim=claim,
                    evidence_ids=[evidence_id],
                    recommendation=recommendation,
                    confidence=0.82 if source == "friction" else 0.86,
                    issue_type="product",
                    priority=self._priority_value(None, severity),
                    page=evidence_item.url if evidence_item else "",
                    current_behavior=claim,
                    expected_behavior=self._expected_behavior(theme, language),
                    repro_steps=self._scenario_repro_steps(result),
                    acceptance_criteria=self._acceptance_criteria(theme, recommendation, language),
                    screenshot_refs=self._screenshot_refs_for_item(evidence_item) if evidence_item else [],
                    source="browser_run_summary",
                    confidence_reason="Extracted from browser-use final summary and linked to the final run evidence.",
                )
            )
        return findings

    def _page_evidence_findings_for_result(self, result: WalkthroughResult, language: str) -> list[Finding]:
        findings: list[Finding] = []
        for item in result.evidence:
            data = item.data if isinstance(item.data, dict) else {}
            page_evidence = data.get("page_evidence")
            if not isinstance(page_evidence, dict):
                continue

            page = str(page_evidence.get("url") or item.url or "")
            page_label = self._page_label(page, page_evidence.get("title") or item.title)
            evidence_ids = [item.id]
            screenshots = self._screenshot_refs_for_item(item)
            status = str(page_evidence.get("status") or "").lower()
            errors = self._text_list(page_evidence.get("errors"))

            if status in {"partial", "failed"} or errors:
                severity = "medium" if status != "failed" else "high"
                reason = "; ".join(errors[:2]) or f"page evidence status is {status or 'unknown'}"
                findings.append(
                    Finding(
                        id=f"fn-{slugify(result.product)}-{result.scenario_id}-{slugify(item.id)}-evidence-reliability",
                        product=result.product,
                        scenario_id=result.scenario_id,
                        severity=severity,
                        theme="Evidence collection reliability",
                        claim=f"Page evidence for {page_label} was incomplete: {reason}",
                        evidence_ids=evidence_ids,
                        recommendation=(
                            "复跑该页面采集，确认是否为环境/登录/加载问题；不要把不完整采集当作产品结论。"
                            if language == "zh"
                            else "Replay evidence collection for this page and avoid treating incomplete capture as a product conclusion."
                        ),
                        confidence=0.74,
                        issue_type="system_reliability",
                        priority=self._priority_value(None, severity),
                        page=page,
                        current_behavior=reason,
                        expected_behavior=(
                            "页面证据应完整包含文本、交互元素、截图和采集状态。"
                            if language == "zh"
                            else "Page evidence should include text, interactive elements, screenshots, and a completed capture status."
                        ),
                        repro_steps=[f"Open {page_label}", "Run page evidence capture for the observed URL."],
                        acceptance_criteria=[
                            "采集状态为 completed，且 manifest、text、elements、screenshot 均可读取。"
                            if language == "zh"
                            else "Capture status is completed and manifest, text, elements, and screenshots are readable."
                        ],
                        screenshot_refs=screenshots,
                        source="page_evidence",
                        confidence_reason="Derived from page evidence status/errors instead of final LLM prose.",
                    )
                )

            page_error_count = self._int_value(page_evidence.get("page_error_count"))
            if page_error_count > 0:
                findings.append(
                    Finding(
                        id=f"fn-{slugify(result.product)}-{result.scenario_id}-{slugify(item.id)}-page-errors",
                        product=result.product,
                        scenario_id=result.scenario_id,
                        severity="high",
                        theme="Page runtime errors",
                        claim=f"{page_label} produced {page_error_count} browser page error(s) during read-only capture.",
                        evidence_ids=evidence_ids,
                        recommendation=(
                            "定位前端运行时错误，补充错误态与回归用例，确认关键路径不再抛错。"
                            if language == "zh"
                            else "Fix the runtime errors, add regression coverage, and confirm the critical path no longer throws."
                        ),
                        confidence=0.82,
                        issue_type="product",
                        priority="P1",
                        page=page,
                        current_behavior=f"{page_error_count} page error(s) were captured.",
                        expected_behavior=(
                            "关键页面在走查和只读采集期间不应产生未处理运行时错误。"
                            if language == "zh"
                            else "Critical pages should not emit unhandled runtime errors during walkthrough and read-only capture."
                        ),
                        repro_steps=[f"Open {page_label}", "Capture console/page errors during the walkthrough."],
                        acceptance_criteria=[
                            "同一页面复跑时 page_error_count 为 0。"
                            if language == "zh"
                            else "A replay of the same page reports page_error_count = 0."
                        ],
                        screenshot_refs=screenshots,
                        source="page_evidence",
                        confidence_reason="Derived from captured page_error_count.",
                    )
                )

            high_risk_controls = self._high_risk_controls(page_evidence)
            if high_risk_controls:
                labels = ", ".join(high_risk_controls[:8])
                recommendation = (
                    "将变更型/破坏型操作按角色、状态和二次确认进行隔离；只读走查下应隐藏或禁用高风险按钮。"
                    if language == "zh"
                    else "Gate mutating/destructive controls by role, state, and confirmation; hide or disable them in read-only walkthrough contexts."
                )
                findings.append(
                    Finding(
                        id=f"fn-{slugify(result.product)}-{result.scenario_id}-{slugify(item.id)}-high-risk-controls",
                        product=result.product,
                        scenario_id=result.scenario_id,
                        severity="high",
                        theme="Permission and destructive controls",
                        claim=f"High-risk controls are visible on {page_label}: {labels}.",
                        evidence_ids=evidence_ids,
                        recommendation=recommendation,
                        confidence=0.8,
                        issue_type="product",
                        priority="P1",
                        page=page,
                        current_behavior=f"Visible controls include: {labels}.",
                        expected_behavior=self._expected_behavior("Permission and destructive controls", language),
                        repro_steps=[f"Open {page_label}", "Inspect visible buttons, links, and menu items without performing mutations."],
                        acceptance_criteria=self._acceptance_criteria(
                            "Permission and destructive controls",
                            recommendation,
                            language,
                        ),
                        screenshot_refs=screenshots,
                        source="page_evidence",
                        confidence_reason="Detected from captured page controls/entries, independent of browser-use final prose.",
                    )
                )

            uncovered_high_risk = self._uncovered_high_risk_entries(page_evidence)
            if uncovered_high_risk:
                labels = ", ".join(uncovered_high_risk[:8])
                findings.append(
                    Finding(
                        id=f"fn-{slugify(result.product)}-{result.scenario_id}-{slugify(item.id)}-coverage-gap",
                        product=result.product,
                        scenario_id=result.scenario_id,
                        severity="medium",
                        theme="High-risk coverage gap",
                        claim=f"High-risk entries were discovered but not safely validated on {page_label}: {labels}.",
                        evidence_ids=evidence_ids,
                        recommendation=(
                            "为这些入口增加沙箱账号、请求拦截或确认弹窗断言，确保后续自动走查可以验证而不产生真实变更。"
                            if language == "zh"
                            else "Add sandbox accounts, request interception, or confirmation assertions so future walkthroughs can validate these entries without real mutations."
                        ),
                        confidence=0.76,
                        issue_type="coverage",
                        priority="P2",
                        page=page,
                        current_behavior=f"Discovered but unvalidated entries: {labels}.",
                        expected_behavior=(
                            "高风险入口应有安全探测策略和明确断言，而不是只停留在发现状态。"
                            if language == "zh"
                            else "High-risk entries should have safe probing strategies and explicit assertions instead of remaining only discovered."
                        ),
                        repro_steps=[f"Open {page_label}", "Review page evidence entries marked unvisited or unsafe."],
                        acceptance_criteria=[
                            "每个高风险入口都有安全探测策略、预期结果和阻断真实变更的保护。"
                            if language == "zh"
                            else "Each high-risk entry has a safe probing strategy, expected result, and protection against real mutation."
                        ],
                        screenshot_refs=screenshots,
                        source="page_evidence",
                        confidence_reason="Detected from page evidence entries whose status remained unvisited/unsafe.",
                    )
                )

            empty_state = self._empty_state_issue(page_evidence)
            if empty_state:
                findings.append(
                    Finding(
                        id=f"fn-{slugify(result.product)}-{result.scenario_id}-{slugify(item.id)}-empty-state",
                        product=result.product,
                        scenario_id=result.scenario_id,
                        severity="medium",
                        theme="Empty-state guidance",
                        claim=f"{page_label} appears to show an empty state without enough next-step guidance.",
                        evidence_ids=evidence_ids,
                        recommendation=(
                            "解释空状态原因，并提供可尝试的筛选、创建或返回路径。"
                            if language == "zh"
                            else "Explain why the state is empty and provide filters, creation paths, or navigation users can try next."
                        ),
                        confidence=0.68,
                        issue_type="product",
                        priority="P2",
                        page=page,
                        current_behavior=empty_state,
                        expected_behavior=self._expected_behavior("Empty-state guidance", language),
                        repro_steps=[f"Open {page_label}", "Observe the page copy when the captured result set is empty."],
                        acceptance_criteria=self._acceptance_criteria(
                            "Empty-state guidance",
                            self._fallback_recommendation("Empty-state guidance", "friction", language),
                            language,
                        ),
                        screenshot_refs=screenshots,
                        source="page_evidence",
                        confidence_reason="Detected from captured visible text containing empty-state markers.",
                    )
                )
        return findings

    def _step_status_findings_for_result(self, result: WalkthroughResult, language: str) -> list[Finding]:
        findings: list[Finding] = []
        for step in result.steps:
            if step.status not in {"friction", "blocked"}:
                continue
            severity = "high" if step.status == "blocked" else "medium"
            theme = "Completion blocker" if step.status == "blocked" else "Experience friction"
            recommendation = self._recommendation(step.status, language)
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-{step.index}",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity=severity,
                    theme=theme,
                    claim=step.observation,
                    evidence_ids=step.evidence_ids,
                    recommendation=recommendation,
                    confidence=0.75 if step.status == "friction" else 0.85,
                    issue_type="product",
                    priority=self._priority_value(None, severity),
                    page=step.url,
                    current_behavior=step.observation,
                    expected_behavior=self._expected_behavior(theme, language),
                    repro_steps=[f"Step {step.index}: {step.action}"],
                    acceptance_criteria=self._acceptance_criteria(theme, recommendation, language),
                    screenshot_refs=[step.screenshot] if step.screenshot else [],
                    source="walk_step_status",
                    confidence_reason="Derived from the walkthrough step status.",
                )
            )
        return findings

    def _final_summary_payload(self, result: WalkthroughResult) -> tuple[dict[str, Any] | None, str | None]:
        candidates: list[tuple[str, str]] = []
        for item in result.evidence:
            if item.kind == "browser_run":
                final_output = item.data.get("final_output")
                if isinstance(final_output, str):
                    candidates.append((final_output, item.id))
                candidates.append((item.summary, item.id))
        for item in result.evidence:
            if item.kind == "browser_step":
                candidates.append((item.summary, item.id))

        for text, evidence_id in candidates:
            payload = self._parse_first_json_object(text)
            if payload and self._looks_like_walkthrough_summary(payload):
                return payload, evidence_id
        return None, None

    def _parse_first_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        return None
                    return payload if isinstance(payload, dict) else None
        return None

    def _looks_like_walkthrough_summary(self, payload: dict[str, Any]) -> bool:
        keys = set(payload)
        return bool(
            keys
            & {
                "completed",
                "status",
                "issues",
                "product_issues",
                "findings",
                "blockers",
                "friction_points",
                "top_recommendations",
                "evidence_needed",
                "checklist",
                "coverage",
            }
        )

    def _as_text_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            parts: list[str] = []
            for key in ("area", "section", "title", "detail", "claim", "summary", "status"):
                item = value.get(key)
                if item:
                    parts.append(str(item))
            if parts:
                return [": ".join(parts)]
            return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                items.extend(self._as_text_list(item))
            return items
        return [str(value)]

    def _classify_issue(self, claim: str, source: str) -> tuple[str, str]:
        text = claim.lower()
        if any(keyword in text for keyword in ("secret", "api key", "token", "password", "credential", "private")):
            return "high", "Secret handling/admin safety"
        if any(keyword in text for keyword in DESTRUCTIVE_KEYWORDS) or "permission" in text:
            return "high", "Permission and destructive controls"
        if any(keyword in text for keyword in ("runtime error", "page error", "console error", "javascript")):
            return "high", "Page runtime errors"
        if any(keyword in text for keyword in ("loading", "spinner", "old content", "navigation", "navigate", "submenu", "route")):
            return "medium", "Navigation and loading feedback"
        if any(keyword in text for keyword in ("empty", "no data", "no-data", "total 0", "0 results")):
            return "medium", "Empty-state guidance"
        if any(keyword in text for keyword in ("external", "documentation", "help center", "support link", "leaving")):
            return "medium", "External-link clarity"
        if source == "blocker":
            return "high", "Completion blocker"
        return "medium", "Experience friction"

    def _recommendation(self, status: str, language: str) -> str:
        if language == "zh":
            if status == "blocked":
                return "用真实浏览器复跑并截取失败页面，同时明确该阻塞点的产品负责人。"
            return "在该步骤周围补充更清晰的引导、校验或成功反馈。"
        if status == "blocked":
            return "Run a real browser replay, capture the failing screen, and define the product owner for the blocker."
        return "Add clearer guidance, validation, or success feedback around this step."

    def _fallback_recommendation(self, theme: str, source: str, language: str) -> str:
        english_fallbacks = {
            "Secret handling/admin safety": "Mask sensitive values by default, require an explicit reveal action, and log/audit access.",
            "Permission and destructive controls": "Gate mutating controls by role and add clear confirmation before destructive or export actions.",
            "Navigation and loading feedback": "Use section-specific loading states and update navigation/content feedback promptly after clicks.",
            "Empty-state guidance": "Explain why the state is empty and provide safe next steps or filters users can try.",
            "External-link clarity": "Label external destinations clearly before opening documentation, help, or support links.",
            "Completion blocker": "Capture a replay and assign an owner to remove the blocker before relying on this flow.",
            "Page runtime errors": "Fix the runtime errors and add regression checks for the affected page.",
            "High-risk coverage gap": "Add a safe probing strategy before relying on this flow for release decisions.",
        }
        chinese_fallbacks = {
            "Secret handling/admin safety": "默认隐藏敏感值，要求用户执行明确的查看动作，并记录访问审计日志。",
            "Permission and destructive controls": "按角色限制可变更操作，并在删除、导出、打款等高风险动作前加入清晰确认。",
            "Navigation and loading feedback": "使用分区级加载状态，并在点击后及时更新导航和内容反馈。",
            "Empty-state guidance": "说明当前为空的原因，并给出安全的下一步操作或可尝试的筛选条件。",
            "External-link clarity": "在打开文档、帮助或支持链接前，明确标注外部目的地。",
            "Completion blocker": "补充回放证据并指定负责人，在依赖该流程前先移除阻塞点。",
            "Page runtime errors": "修复页面运行时错误，并为受影响页面补充回归检查。",
            "High-risk coverage gap": "在依赖该流程做发布判断前，补充安全探测策略。",
        }
        fallbacks = chinese_fallbacks if language == "zh" else english_fallbacks
        if source == "blocker":
            return fallbacks.get(theme, fallbacks["Completion blocker"])
        default = (
            "在该区域补充更清晰的引导、校验或成功反馈。"
            if language == "zh"
            else "Add clearer guidance, validation, or success feedback around this area."
        )
        return fallbacks.get(theme, default)

    def _best_recommendation(
        self,
        claim: str,
        recommendations: list[str],
        fallback: str,
        theme: str,
        minimum_score: int = 1,
    ) -> str:
        if not recommendations:
            return fallback
        claim_tokens = self._tokens(claim)
        best = ""
        best_score = 0
        for recommendation in recommendations:
            if not self._recommendation_matches_theme(recommendation, theme):
                continue
            score = len(claim_tokens & self._tokens(recommendation))
            if score > best_score:
                best = recommendation
                best_score = score
        return best if best_score >= minimum_score else fallback

    def _recommendation_matches_theme(self, recommendation: str, theme: str) -> bool:
        text = recommendation.lower()
        theme_keywords = {
            "Secret handling/admin safety": ("secret", "key", "token", "mask", "private", "sensitive", "audit", "reveal", "credential"),
            "Permission and destructive controls": ("permission", "mutat", "export", "add", "edit", "archive", "disable", "save", "payout", "bank", "control", "gate"),
            "Navigation and loading feedback": ("loading", "route", "navigation", "settings", "skeleton", "spinner", "category", "progress"),
            "Empty-state guidance": ("empty", "no data", "guidance", "next step", "filter"),
            "External-link clarity": ("external", "link", "domain", "documentation", "help", "support"),
            "Page runtime errors": ("error", "runtime", "regression", "console"),
        }
        keywords = theme_keywords.get(theme)
        if not keywords:
            return True
        return any(keyword in text for keyword in keywords)

    def _expected_behavior(self, theme: str, language: str) -> str:
        english = {
            "Secret handling/admin safety": "Sensitive values are masked by default and only revealed through explicit audited intent.",
            "Permission and destructive controls": "Risky controls are hidden, disabled, or confirmation-gated unless the role and state allow safe mutation.",
            "Navigation and loading feedback": "Navigation gives immediate, page-specific feedback and never leaves stale content looking current.",
            "Empty-state guidance": "Empty states explain why there is no data and give a safe next step.",
            "External-link clarity": "External links clearly disclose the destination before opening another domain.",
            "Completion blocker": "The user can complete the target journey without manual rescue.",
            "Page runtime errors": "The page runs without unhandled browser errors on the critical path.",
        }
        chinese = {
            "Secret handling/admin safety": "敏感值默认被隐藏，只有通过明确且可审计的查看动作才会展示。",
            "Permission and destructive controls": "高风险操作会按角色和状态隐藏、禁用或二次确认，避免误触发真实变更。",
            "Navigation and loading feedback": "导航后立即给出页面级反馈，不让旧内容看起来像当前内容。",
            "Empty-state guidance": "空状态说明无数据原因，并提供安全下一步。",
            "External-link clarity": "打开外部域名前明确告知目的地。",
            "Completion blocker": "用户可以在无需人工救援的情况下完成目标旅程。",
            "Page runtime errors": "关键路径页面不出现未处理浏览器运行时错误。",
        }
        return (chinese if language == "zh" else english).get(theme, self._fallback_recommendation(theme, "friction", language))

    def _acceptance_criteria(self, theme: str, recommendation: str, language: str) -> list[str]:
        if language == "zh":
            return [
                "复跑同一场景时问题不再出现，并有截图或页面证据佐证。",
                f"实现动作：{recommendation}",
            ]
        return [
            "A replay of the same scenario no longer reproduces the issue and includes screenshot or page evidence.",
            f"Implemented action: {recommendation}",
        ]

    def _high_risk_controls(self, page_evidence: dict[str, Any]) -> list[str]:
        labels: list[str] = []
        for value in page_evidence.get("key_controls") or page_evidence.get("controls") or []:
            if self._looks_high_risk_label(str(value)):
                labels.append(self._clean_text(str(value)))
        for entry in page_evidence.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            label = self._entry_label(entry)
            kind = str(entry.get("kind") or "").lower()
            if label and (kind == "destructive" or self._looks_high_risk_label(label)):
                labels.append(label)
        return self._unique_text(labels)

    def _uncovered_high_risk_entries(self, page_evidence: dict[str, Any]) -> list[str]:
        labels: list[str] = []
        for entry in page_evidence.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").lower()
            if status not in {"unvisited", "unsafe", "blocked"}:
                continue
            label = self._entry_label(entry)
            if label and self._looks_high_risk_label(label):
                labels.append(label)
        return self._unique_text(labels)

    def _empty_state_issue(self, page_evidence: dict[str, Any]) -> str:
        text_candidates = [
            str(page_evidence.get("text_excerpt") or ""),
            " ".join(self._text_list(page_evidence.get("text_observations"))),
            str(page_evidence.get("summary") or ""),
        ]
        text = " ".join(text_candidates)
        lowered = text.lower()
        if not any(marker in lowered for marker in ("no data", "no records", "no results", "empty", "0 results", "total 0")):
            return ""
        if any(marker in lowered for marker in ("create", "add", "adjust filter", "clear filter", "try another", "learn more")):
            return ""
        return self._clean_text(text)[:240]

    def _entry_label(self, entry: dict[str, Any]) -> str:
        return self._clean_text(
            str(entry.get("label") or entry.get("text") or entry.get("aria_label") or entry.get("title") or "")
        )

    def _looks_high_risk_label(self, label: str) -> bool:
        lowered = label.lower()
        return any(keyword in lowered for keyword in DESTRUCTIVE_KEYWORDS)

    def _checklist_stats(self, results: list[WalkthroughResult]) -> dict[str, int | float]:
        total = passed = failed = untested = 0
        for result in results:
            payload, _ = self._final_summary_payload(result)
            raw_items = payload.get("checklist") if payload else None
            if not isinstance(raw_items, list):
                continue
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                total += 1
                status = str(raw_item.get("status") or "").lower()
                if status in {"pass", "passed", "completed", "ok", "true"}:
                    passed += 1
                elif status in {"fail", "failed", "blocked", "false"}:
                    failed += 1
                else:
                    untested += 1
        return {
            "checklist_total": total,
            "checklist_passed": passed,
            "checklist_failed": failed,
            "checklist_untested": untested,
            "checklist_pass_rate": round(passed / total, 3) if total else 0.0,
        }

    def _issue_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"claim": value}
        return {}

    def _issue_type(self, issue: dict[str, Any], *, default: str) -> str:
        raw = str(issue.get("issue_type") or issue.get("type") or default).strip().lower().replace("-", "_")
        aliases = {
            "system": "system_reliability",
            "reliability": "system_reliability",
            "runtime": "system_reliability",
            "coverage_gap": "coverage",
            "gap": "coverage",
            "product_issue": "product",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in {"product", "coverage", "system_reliability", "positive"} else default

    def _priority_value(self, value: Any, severity: str) -> str:
        text = str(value or "").strip().upper()
        if text in {"P0", "P1", "P2", "P3", "P4"}:
            return text
        return {"high": "P1", "medium": "P2", "low": "P3", "info": "P4"}.get(severity.lower(), "P2")

    def _severity_value(self, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        aliases = {"critical": "high", "p0": "high", "p1": "high", "p2": "medium", "p3": "low"}
        text = aliases.get(text, text)
        return text if text in {"high", "medium", "low", "info"} else None

    def _confidence_value(self, value: Any, *, default: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return default
        return round(min(max(confidence, 0.0), 1.0), 2)

    def _int_value(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _evidence_ids(self, value: Any, fallback: str | None) -> list[str]:
        ids = [item for item in self._text_list(value) if item]
        if not ids and fallback:
            ids = [fallback]
        return self._unique_text(ids)

    def _text_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [self._clean_text(value)] if self._clean_text(value) else []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                result.extend(self._text_list(item))
            return result
        if isinstance(value, dict):
            label = self._clean_text(
                str(value.get("label") or value.get("title") or value.get("summary") or value.get("claim") or "")
            )
            return [label] if label else []
        return [self._clean_text(str(value))]

    def _tokens(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 4}

    def _is_non_issue(self, claim: str) -> bool:
        text = claim.lower()
        non_issue_markers = [
            "no hard access blocker",
            "no hard access blockers",
            "no hard blocker",
            "no hard blockers",
            "no blocker",
            "no blockers",
            "without a login prompt",
            "authentication was already active",
            "intentionally not opened",
            "per instruction",
            "not verified",
        ]
        return any(marker in text for marker in non_issue_markers)

    def _clean_text(self, text: str) -> str:
        return " ".join(str(text).strip().split())

    def _normalize_claim(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _unique_text(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            cleaned = self._clean_text(value)
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
        return result

    def _dedupe_findings(self, findings: list[Finding]) -> list[Finding]:
        by_key: dict[tuple[str, str, str], Finding] = {}
        for finding in findings:
            key = (
                finding.issue_type,
                finding.theme.lower(),
                self._normalize_claim(finding.claim),
            )
            existing = by_key.get(key)
            if existing is None or finding.confidence > existing.confidence:
                by_key[key] = finding
                continue
            for evidence_id in finding.evidence_ids:
                if evidence_id not in existing.evidence_ids:
                    existing.evidence_ids.append(evidence_id)
            for screenshot_ref in finding.screenshot_refs:
                if screenshot_ref not in existing.screenshot_refs:
                    existing.screenshot_refs.append(screenshot_ref)
        return list(by_key.values())

    def _scenario_repro_steps(self, result: WalkthroughResult) -> list[str]:
        steps = [f"Step {step.index}: {step.action}" for step in result.steps[:6] if step.action]
        return steps or [f"Run scenario {result.scenario_id}: {result.scenario_title}"]

    def _screenshot_refs_for_item(self, item: Any) -> list[str]:
        if item is None:
            return []
        refs: list[str] = []
        screenshot = getattr(item, "screenshot", None)
        if isinstance(screenshot, str) and screenshot:
            refs.append(screenshot)
        data = getattr(item, "data", {})
        if isinstance(data, dict):
            for key in ("screenshot_path", "full_page_screenshot_path", "viewport_screenshot_path"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    refs.append(value)
            screenshot_paths = data.get("screenshot_paths")
            if isinstance(screenshot_paths, list):
                refs.extend(str(path) for path in screenshot_paths if str(path).strip())
            page_evidence = data.get("page_evidence")
            if isinstance(page_evidence, dict):
                for key in ("full_page_screenshot_path", "viewport_screenshot_path"):
                    value = page_evidence.get(key)
                    if isinstance(value, str) and value:
                        refs.append(value)
                refs.extend(self._text_list(page_evidence.get("screenshot_paths")))
        return self._unique_text(refs)

    def _evidence_by_id(self, result: WalkthroughResult, evidence_id: str) -> Any | None:
        return next((item for item in result.evidence if item.id == evidence_id), None)

    def _page_label(self, url: str, title: Any) -> str:
        title_text = self._clean_text(str(title or ""))
        if title_text:
            return title_text
        try:
            parsed = urlparse(url)
        except Exception:
            return url or "the page"
        if not parsed.netloc:
            return url or "the page"
        path = parsed.path or "/"
        return f"{parsed.netloc}{path}"

    def _avg(self, values: object) -> float:
        items = [float(value) for value in values]
        return sum(items) / len(items) if items else 0.0


class CompetitiveAnalyst:
    def compare(
        self,
        results: list[WalkthroughResult],
        evidence: list[Any],
        language: str = "en",
    ) -> list[CompetitiveInsight]:
        language = normalize_report_language(language)
        by_scenario: dict[str, list[WalkthroughResult]] = defaultdict(list)
        for result in results:
            by_scenario[result.scenario_id].append(result)

        insights: list[CompetitiveInsight] = []
        for scenario_id, scenario_results in by_scenario.items():
            if len(scenario_results) < 2:
                continue
            sorted_by_completion = sorted(
                scenario_results,
                key=lambda item: float(item.metrics.get("completion_score", 0)),
                reverse=True,
            )
            leader = sorted_by_completion[0]
            laggard = sorted_by_completion[-1]
            if leader.product == laggard.product:
                continue
            evidence_ids = []
            if leader.evidence:
                evidence_ids.append(leader.evidence[0].id)
            if laggard.evidence:
                evidence_ids.append(laggard.evidence[0].id)
            if language == "zh":
                theme = f"场景：{leader.scenario_title}"
                claim = f"{leader.product} 在 {scenario_id} 场景中的完成信号最强，{laggard.product} 的完成信号最弱。"
                recommendation = "把领先流程作为参考，并重点检查最弱流程是否缺少引导、存在阻塞或步骤过多。"
            else:
                theme = f"Scenario: {leader.scenario_title}"
                claim = (
                    f"{leader.product} had the strongest completion signal for "
                    f"{scenario_id}, while {laggard.product} showed the weakest signal."
                )
                recommendation = (
                    "Use the leader flow as a reference and inspect the weakest flow "
                    "for missing guidance, blockers, or excessive steps."
                )
            insights.append(
                CompetitiveInsight(
                    theme=theme,
                    claim=claim,
                    products=[leader.product, laggard.product],
                    evidence_ids=evidence_ids,
                    recommendation=recommendation,
                    confidence=0.7,
                )
            )
        return insights
