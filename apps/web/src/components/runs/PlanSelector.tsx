import type { PlanSummary } from "../../types/contracts";

interface PlanSelectorProps {
  plans: PlanSummary[];
  selectedPlanId: string;
  onPlanChange: (planId: string) => void;
}

export function PlanSelector({ plans, selectedPlanId, onPlanChange }: PlanSelectorProps) {
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId || plan.path === selectedPlanId);

  return (
    <>
      <label className="field">
        <span>走查计划</span>
        <select value={selectedPlanId} onChange={(event) => onPlanChange(event.target.value)} disabled={plans.length === 0}>
          {plans.length === 0 ? <option value="">暂无可用计划</option> : null}
          {plans.map((plan) => (
            <option key={plan.id} value={plan.id}>
              {plan.path}
            </option>
          ))}
        </select>
      </label>

      <div className="plan-summary">
        {selectedPlan ? (
          <>
            <strong>{selectedPlan.title}</strong>
            <div className="metric-row">
              <span>{selectedPlan.product_count} 个产品</span>
              <span>{selectedPlan.scenario_count} 个场景</span>
              <span>{selectedPlan.report_language} 报告</span>
            </div>
          </>
        ) : (
          <p className="empty-copy">尚未选择本地计划。</p>
        )}
      </div>
    </>
  );
}
