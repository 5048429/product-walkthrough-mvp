import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import type { ConsoleStatus, EvaluationResponse, RunSummary } from "../../types/contracts";

interface EvaluationSummaryProps {
  evaluation: EvaluationResponse | null;
  run: RunSummary | null;
  status: ConsoleStatus;
  loading?: boolean;
  error?: string | null;
  viewingHistory?: boolean;
}

function formatScore(value: number): string {
  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function formatScoreLabel(key: string): string {
  const labels: Record<string, string> = {
    task_completion_rate: "场景完成率",
    evidence_coverage_rate: "证据覆盖率",
    finding_grounding_rate: "问题证据关联率",
    recommendation_actionability_rate: "建议可执行率",
    issue_schema_completeness_rate: "问题字段完整率",
    screenshot_grounding_rate: "截图佐证率",
    checklist_coverage_rate: "清单覆盖率",
    checklist_pass_rate: "清单通过率",
    page_evidence_success_rate: "页面证据成功率",
    page_evidence_partial_rate: "页面证据部分失败率",
    page_evidence_failed_rate: "页面证据失败率",
    timeout_rate: "超时率",
    invalid_summary_rate: "无效摘要率",
    evidence_quality_score: "证据质量",
    quality_gate_passed: "质量门禁",
    evidence_items: "证据条数",
    findings: "发现总数",
    issues: "问题总数",
    product_issues: "产品问题",
    coverage_gaps: "覆盖缺口",
    system_reliability_issues: "可靠性限制",
    critical_issues: "关键问题",
  };

  return labels[key] ?? key.replaceAll("_", " ");
}

export function EvaluationSummary({
  evaluation,
  run,
  status,
  loading = false,
  error,
  viewingHistory = false,
}: EvaluationSummaryProps) {
  return (
    <section className="panel compact-panel" aria-labelledby="evaluation-summary-title">
      <div className="panel-header">
        <div>
          <h2 id="evaluation-summary-title">评估</h2>
          <p>
            {run
              ? `${viewingHistory ? "历史" : "当前"}任务 / ${evaluation?.artifact_id ?? "evaluation.json"}`
              : "尚未选择任务"}
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      {loading && !evaluation ? (
        <EmptyState title="正在读取评估" message="正在从 API 读取 evaluation.json。" compact />
      ) : null}
      {error && !evaluation ? (
        <ErrorState
          title="评估不可用"
          message="该任务缺少 evaluation.json，或文件暂时不可读取。"
          details={error}
          compact
        />
      ) : null}
      {!loading && !error && !evaluation ? (
        <EmptyState
          title="尚未选择评估"
          message="启动一次任务，或选择带有 evaluation.json 的历史任务。"
          compact
        />
      ) : null}

      {evaluation ? (
        <>
          <div className="score-display">{formatScore(evaluation.overall_score)}</div>
          {evaluation.quality_gate_status ? (
            <div className={`partial-banner partial-banner-${evaluation.quality_gate_status === "pass" ? "running" : "blocked"}`}>
              <strong>质量门禁：{evaluation.quality_gate_status}</strong>
              <span>用于判断本次结论是否足以替代人工走查。</span>
            </div>
          ) : null}
          <dl className="score-list">
            {Object.entries(evaluation.scores).map(([key, value]) => (
              <div key={key}>
                <dt>{formatScoreLabel(key)}</dt>
                <dd>{formatScore(value)}</dd>
              </div>
            ))}
          </dl>
          {evaluation.notes.length > 0 ? (
            <ul className="notes-list">
              {evaluation.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : (
            <EmptyState title="暂无备注" message="评估文件没有提供额外备注。" compact />
          )}
        </>
      ) : null}
    </section>
  );
}
