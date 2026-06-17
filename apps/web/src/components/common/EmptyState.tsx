import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  message: string;
  action?: ReactNode;
  compact?: boolean;
}

export function EmptyState({ title, message, action, compact = false }: EmptyStateProps) {
  return (
    <div className={`state-panel empty-state ${compact ? "state-panel-compact" : ""}`.trim()}>
      <strong>{title}</strong>
      <p>{message}</p>
      {action ? <div className="state-action">{action}</div> : null}
    </div>
  );
}
