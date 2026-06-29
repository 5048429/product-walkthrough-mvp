import type { ReportResponse } from "../types/contracts";
import { mockArtifacts } from "./artifacts";

export const mockReport: ReportResponse = {
  run_id: "run-20260616-163039-a33a65",
  language: "zh",
  markdown_artifact_id: "art_report_md",
  evaluation_artifact_id: "art_evaluation_json",
  issues_artifact_id: "art_issues_json",
  generated_at: "2026-06-16T08:31:15Z",
  artifacts: mockArtifacts,
  evaluation: {
    overall_score: 0.92,
    quality_gate_status: "warn",
    scores: {
      task_completion_rate: 0.83,
      evidence_coverage_rate: 1,
      finding_grounding_rate: 0.9,
      recommendation_actionability_rate: 0.95,
      issue_schema_completeness_rate: 1,
      evidence_quality_score: 0.86,
      quality_gate_passed: 0,
      evidence_items: 2,
      findings: 3,
      issues: 3,
    },
    notes: [
      "Mock 数据覆盖报告、证据、评估和事件预览路径。",
      "截图产物刻意缺失，用于验证缺失态 UI。",
    ],
  },
  issues: {
    run_id: "run-20260616-163039-a33a65",
    artifact_id: "art_issues_json",
    created_at: "2026-06-16T08:31:15Z",
    report_language: "zh",
    schema_version: "1.0",
    summary: {
      issue_count: 3,
      product_issue_count: 2,
      coverage_gap_count: 1,
      system_reliability_issue_count: 0,
      priority_counts: { P1: 1, P2: 2 },
      severity_counts: { high: 1, medium: 2 },
      type_counts: { product: 2, coverage: 1 },
    },
    checklist: [
      {
        id: "pm-check-1",
        title: "关键页面可以正常加载并保留可读截图证据",
        status: "pass",
        source: "mock",
        severity: "high",
        evidence_ids: ["ev-our-product-onboarding-1"],
        notes: "主路径保留了证据。",
      },
    ],
    issues: [
      {
        id: "fn-mock-p1",
        product: "Owned Product",
        scenario_id: "onboarding",
        severity: "high",
        theme: "Permission and destructive controls",
        claim: "设置页在只读走查中仍暴露高风险保存操作。",
        evidence_ids: ["ev-our-product-onboarding-1"],
        recommendation: "按角色和状态禁用变更型操作，并在可执行前加入二次确认。",
        confidence: 0.84,
        issue_type: "product",
        priority: "P1",
        page: "Settings",
        current_behavior: "只读上下文可见保存按钮。",
        expected_behavior: "只读上下文隐藏或禁用变更型操作。",
        repro_steps: ["打开设置页", "检查可见按钮"],
        acceptance_criteria: ["只读角色无法触发保存动作"],
        screenshot_refs: [],
        source: "mock",
        confidence_reason: "由 mock 证据模拟。",
      },
      {
        id: "fn-mock-p2",
        product: "Competitor",
        scenario_id: "project",
        severity: "medium",
        theme: "Navigation and loading feedback",
        claim: "项目创建前要求选择模板，延后了进入工作台的时间。",
        evidence_ids: ["ev-competitor-project-1"],
        recommendation: "允许先创建基础工作台，再引导用户选择模板。",
        confidence: 0.78,
        issue_type: "product",
        priority: "P2",
        page: "Project setup",
        current_behavior: "必须先完成模板选择。",
        expected_behavior: "用户可以更快进入可操作状态。",
        repro_steps: ["进入项目创建", "观察模板步骤"],
        acceptance_criteria: ["基础创建路径无需强制模板选择"],
        screenshot_refs: [],
        source: "mock",
        confidence_reason: "由 mock 证据模拟。",
      },
      {
        id: "fn-mock-gap",
        product: "Competitor",
        scenario_id: "checkout",
        severity: "medium",
        theme: "High-risk coverage gap",
        claim: "Checkout 恢复流程被人工验证阻断，缺少安全复跑策略。",
        evidence_ids: ["ev-competitor-checkout-blocked"],
        recommendation: "配置测试账号或人工验证 checkpoint 后再复跑该路径。",
        confidence: 0.72,
        issue_type: "coverage",
        priority: "P2",
        page: "Checkout",
        current_behavior: "流程停在人工验证。",
        expected_behavior: "高风险支付路径有安全验证策略。",
        repro_steps: ["打开 Checkout 恢复流程"],
        acceptance_criteria: ["复跑时不触发真实支付且能完成断言"],
        screenshot_refs: [],
        source: "mock",
        confidence_reason: "由 mock 证据模拟。",
      },
    ],
  },
  markdown: `# 产品走查问题报告

## PM 走查汇总

Mock 运行展示了一个自家产品 onboarding 路径和一个竞品项目创建路径。当前结论用于前端预览，不代表真实产品判断。

## 结构化问题板

- P1：设置页在只读走查中仍暴露高风险保存操作。证据：ev-our-product-onboarding-1。
- P2：项目创建前要求选择模板，延后进入工作台。证据：ev-competitor-project-1。
- P2：Checkout 恢复流程被人工验证阻断，缺少安全复跑策略。证据：ev-competitor-checkout-blocked。

## 建议动作

1. 把产品问题、覆盖缺口和系统可靠性限制分开处理。
2. 为高风险入口配置沙箱账号、请求拦截或人工验证 checkpoint。
3. 保留缺失截图状态，让部分证据仍可复核。
`,
};
