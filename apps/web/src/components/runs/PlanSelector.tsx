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
        <span>Plan</span>
        <select value={selectedPlanId} onChange={(event) => onPlanChange(event.target.value)} disabled={plans.length === 0}>
          {plans.length === 0 ? <option value="">No plans available</option> : null}
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
              <span>{selectedPlan.product_count} products</span>
              <span>{selectedPlan.scenario_count} scenarios</span>
              <span>{selectedPlan.report_language} report</span>
            </div>
          </>
        ) : (
          <p className="empty-copy">No local plan selected.</p>
        )}
      </div>
    </>
  );
}
