# Phase 3.2 Frontend Console Components Handoff

## Scope

This phase completed the mock-driven core console components on top of the Phase 3.1 `apps/web` scaffold. No real API calls were added; the UI still reads from local mock data and mock state derivation helpers.

Build verification:

```bash
cd apps/web
npm run build
```

Result: passed.

## Components

### Runs

- `apps/web/src/components/runs/RunStartPanel.tsx`
  - Main start panel for selecting a plan, choosing run mode, setting launch parameters, showing active run progress, and previewing mock request parameters.
  - Props:
    - `plans: PlanSummary[]`
    - `selectedPlanId: string`
    - `activeRun: RunDetail | null`
    - `consoleStatus: ConsoleStatus`
    - `onPlanChange(planId: string): void`
    - `onStatusChange(status: ConsoleStatus): void`

- `apps/web/src/components/runs/PlanSelector.tsx`
  - Local plan selector plus compact summary.
  - Props:
    - `plans: PlanSummary[]`
    - `selectedPlanId: string`
    - `onPlanChange(planId: string): void`

- `apps/web/src/components/runs/RunModeSelector.tsx`
  - Segmented mock/browser-use selector plus browser max steps and verification mode controls.
  - Props:
    - `mode: RunMode`
    - `browserMaxSteps: number`
    - `verificationMode: "off" | "manual"`
    - `onModeChange(mode: RunMode): void`
    - `onBrowserMaxStepsChange(steps: number): void`
    - `onVerificationModeChange(mode: "off" | "manual"): void`

- `apps/web/src/components/runs/RunLauncher.tsx`
  - Kept as a compatibility wrapper around `RunStartPanel` for the Phase 3.1 page scaffold.

### Agents

- `apps/web/src/components/agents/AgentStatusPanel.tsx`
  - Main agent status surface. Shows overall console state, pipeline timeline, empty state, and sorted agent cards.
  - Props:
    - `agents: AgentExecution[]`
    - `consoleStatus?: ConsoleStatus`

- `apps/web/src/components/agents/AgentTimeline.tsx`
  - Pipeline timeline for Director, Planner, Walker, Evidence, Analyst, Reviewer, Reporter, and Evaluator stages.
  - Props:
    - `agents: AgentExecution[]`
    - `consoleStatus: ConsoleStatus`

- `apps/web/src/components/agents/AgentStatusCard.tsx`
  - Per-agent card with label, PM-readable status, current step, step count, heartbeat, completion score, and error/blocker message.
  - Props:
    - `agent: AgentExecution`
    - `consoleStatus: ConsoleStatus`

- `apps/web/src/components/agents/AgentStatusBoard.tsx`
  - Kept as a compatibility wrapper around `AgentStatusPanel`.

Agent status presentation now distinguishes:

- `idle`: no agents and explicit empty state.
- `running`: active running agents and blue status treatment.
- `done`: succeeded/skipped stages render as done.
- `blocked`: waiting agent is promoted to blocked when the run state is blocked.
- `failed`: failed agent and error summary are shown in red.

### Events

- `apps/web/src/components/events/EventLog.tsx`
  - Enhanced event stream with filters by:
    - `level`
    - `event_type`
    - `agent`
    - `status`
  - Shows event sequence, type, level, message, agent, status, product, scenario, artifact IDs, and compact payload summary.
  - Props:
    - `events: RunEvent[]`

## Mock Data

- `apps/web/src/mock/agents.ts`
  - Expanded agent coverage to include evidence extractor, product analyst, reviewer, report writer, and evaluator.
  - Added `getMockAgentsForStatus(status: ConsoleStatus)` to derive mock agent lists for `idle`, `running`, `done`, `blocked`, and `failed`.

- `apps/web/src/mock/events.ts`
  - Expanded event samples to cover stage, scenario step, evidence, blocked, finding, artifact, evaluation, completed, and failed paths.
  - Added `getMockEventsForStatus(status: ConsoleStatus)` so EventLog reflects the selected mock run state.

- `apps/web/src/api/mockConsoleData.ts`
  - Exposes the new mock derivation helpers through `mockConsoleData`.

- `apps/web/src/pages/ConsolePage.tsx`
  - Wires selected mock state into agent and event mock helpers so status preview changes are visible across the workbench.

## Types

No new exported contract types were required. Existing types in `apps/web/src/types/contracts.ts` were sufficient:

- `ConsoleStatus`
- `RunMode`
- `PlanSummary`
- `RunDetail`
- `AgentExecution`
- `RunEvent`

## Not Done

- No real API integration.
- No SSE subscription.
- No route-level navigation or deep links from events to evidence/report.
- No real artifact content loading for screenshots.
- Browser-use and manual verification remain UI/mock entry points only.
- The markdown report preview is still lightweight and not a full markdown renderer.
