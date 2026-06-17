import type { AgentStatus, ConsoleStatus, EventLevel, RunStatus } from "../types/contracts";
import { toConsoleStatus } from "../types/contracts";

type StatusKind = ConsoleStatus | RunStatus | AgentStatus | EventLevel;

interface StatusBadgeProps {
  status: StatusKind;
  label?: string;
}

function normalizeStatus(status: StatusKind): ConsoleStatus | EventLevel | AgentStatus {
  if (
    status === "queued" ||
    status === "starting" ||
    status === "awaiting_verification" ||
    status === "blocked" ||
    status === "finalizing" ||
    status === "succeeded" ||
    status === "canceling" ||
    status === "canceled"
  ) {
    return toConsoleStatus(status);
  }

  if (status === "info" || status === "warn" || status === "error" || status === "debug") {
    return status;
  }

  if (status === "pending" || status === "waiting" || status === "skipped") {
    return status;
  }

  return status;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const normalized = normalizeStatus(status);

  return (
    <span className={`status-badge status-${normalized}`}>
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}
