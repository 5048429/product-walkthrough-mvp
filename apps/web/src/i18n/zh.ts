import type { AgentStatus, AgentType, ArtifactType, ConsoleStatus, EventLevel, RunMode, RunStatus } from "../types/contracts";

export type StatusLike = ConsoleStatus | RunStatus | AgentStatus | EventLevel | string | null | undefined;

const statusLabels: Record<string, string> = {
  idle: "未开始",
  queued: "排队中",
  starting: "启动中",
  running: "运行中",
  awaiting_verification: "等待人工验证",
  blocked: "受阻",
  timeout: "已超时",
  finalizing: "整理产物",
  succeeded: "已完成",
  done: "已完成",
  failed: "失败",
  canceling: "取消中",
  canceled: "已取消",
  pending: "待处理",
  waiting: "等待中",
  skipped: "已跳过",
  debug: "调试",
  info: "信息",
  warn: "警告",
  error: "错误",
};

const agentTypeLabels: Record<AgentType | string, string> = {
  director: "总控",
  planner: "场景规划",
  walker: "页面走查",
  evidence_extractor: "证据整理",
  product_analyst: "产品分析",
  competitive_analyst: "竞品分析",
  reviewer: "审阅",
  report_writer: "报告生成",
  evaluator: "评分",
  auth_session: "登录验证",
};

const eventTypeLabels: Record<string, string> = {
  "run.created": "任务已创建",
  "plan.loaded": "计划已读取",
  "run.started": "任务开始",
  "stage.started": "流程开始",
  "stage.completed": "流程完成",
  "agent.started": "Agent 开始",
  "agent.status_changed": "Agent 状态变化",
  "agent.completed": "Agent 完成",
  "agent.failed": "Agent 失败",
  "scenario.started": "场景开始",
  "scenario.step.started": "步骤开始",
  "scenario.step.completed": "步骤完成",
  "scenario.completed": "场景完成",
  "evidence.created": "证据已创建",
  "screenshot.archived": "截图已归档",
  "finding.created": "发现已创建",
  "artifact.created": "产物已生成",
  "report.generated": "报告已生成",
  "evaluation.generated": "评分已生成",
  "run.awaiting_verification": "等待人工验证",
  "run.blocked": "任务受阻",
  "run.finalizing": "整理产物",
  "run.completed": "任务完成",
  "run.failed": "任务失败",
  "run.timeout": "任务超时",
  "run.canceled": "任务已取消",
};

const artifactTypeLabels: Record<ArtifactType | string, string> = {
  run_manifest: "任务清单",
  plan_json: "走查计划",
  events_jsonl: "事件日志",
  agents_json: "Agent 状态",
  artifacts_json: "产物索引",
  evidence_json: "证据文件",
  report_markdown: "Markdown 报告",
  evaluation_json: "评分文件",
  screenshot: "截图",
  browser_history: "浏览器历史",
  log_text: "日志",
};

const scoreLabels: Record<string, string> = {
  task_completion_rate: "任务完成率",
  evidence_coverage_rate: "证据覆盖率",
  finding_grounding_rate: "发现有证据支撑",
  recommendation_actionability_rate: "建议可执行性",
  overall_score: "综合评分",
};

const evidenceKindLabels: Record<string, string> = {
  observation: "观察",
  browser_run: "浏览器走查",
  browser_step: "浏览器步骤",
  finding: "发现",
};

export function labelStatus(status: StatusLike): string {
  const key = String(status ?? "").trim();
  return statusLabels[key] ?? key.replaceAll("_", " ");
}

export function labelAgentType(type: AgentType | string | null | undefined): string {
  const key = String(type ?? "").trim();
  return agentTypeLabels[key] ?? key.replaceAll("_", " ");
}

export function labelEventType(type: string | null | undefined): string {
  const key = String(type ?? "").trim();
  return eventTypeLabels[key] ?? key.replaceAll(".", " ").replaceAll("_", " ");
}

export function labelArtifactType(type: ArtifactType | string | null | undefined): string {
  const key = String(type ?? "").trim();
  return artifactTypeLabels[key] ?? key.replaceAll("_", " ");
}

export function labelScore(key: string): string {
  return scoreLabels[key] ?? key.replaceAll("_", " ");
}

export function labelEvidenceKind(kind: string | null | undefined): string {
  const key = String(kind ?? "").trim();
  return evidenceKindLabels[key] ?? key.replaceAll("_", " ");
}

export function labelMode(mode: RunMode | string | null | undefined): string {
  if (mode === "mock") {
    return "模拟走查";
  }
  if (mode === "browser-use" || mode === "browser-use-local") {
    return "真实浏览器走查";
  }
  return String(mode ?? "未知模式");
}

export function formatCount(value: number, unit: string): string {
  return `${value} ${unit}`;
}

