import type { ConsoleDataSource, ConsoleErrorState, ConsoleLoadingState, StartRunOptions } from "../../hooks/useProdwalkConsole";
import type { ConsoleStatus, HealthResponse, PlanDetailResponse, PlanSummary } from "../../types/contracts";
import { RunStartPanel } from "./RunStartPanel";

interface RunLauncherProps {
  source: ConsoleDataSource;
  health: HealthResponse | null;
  plans: PlanSummary[];
  selectedPlanId: string;
  selectedPlanDetail: PlanDetailResponse | null;
  consoleStatus: ConsoleStatus;
  authReady: boolean;
  authSessionId: string | null;
  loading: ConsoleLoadingState;
  errors: ConsoleErrorState;
  onPlanChange: (planId: string) => void;
  onStartRun: (options: StartRunOptions) => void;
  onMockStatusChange: (status: ConsoleStatus) => void;
  onRetryApi: () => void;
}

export function RunLauncher({
  source,
  health,
  plans,
  selectedPlanId,
  selectedPlanDetail,
  consoleStatus,
  authReady,
  authSessionId,
  loading,
  errors,
  onPlanChange,
  onStartRun,
  onMockStatusChange,
  onRetryApi,
}: RunLauncherProps) {
  return (
    <RunStartPanel
      source={source}
      health={health}
      plans={plans}
      selectedPlanId={selectedPlanId}
      selectedPlanDetail={selectedPlanDetail}
      consoleStatus={consoleStatus}
      authReady={authReady}
      authSessionId={authSessionId}
      loading={loading}
      errors={errors}
      onPlanChange={onPlanChange}
      onStartRun={onStartRun}
      onMockStatusChange={onMockStatusChange}
      onRetryApi={onRetryApi}
    />
  );
}
