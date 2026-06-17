import type { ReactNode } from "react";

interface ErrorStateProps {
  title: string;
  message: string;
  code?: string;
  details?: string;
  tone?: "failed" | "blocked";
  action?: ReactNode;
  compact?: boolean;
}

export function ErrorState({
  title,
  message,
  code,
  details,
  tone = "failed",
  action,
  compact = false,
}: ErrorStateProps) {
  return (
    <div className={`state-panel error-state error-state-${tone} ${compact ? "state-panel-compact" : ""}`.trim()}>
      <strong>{title}</strong>
      <p>{message}</p>
      {code ? <span className="state-code">{code}</span> : null}
      {details ? <p className="state-details">{details}</p> : null}
      {action ? <div className="state-action">{action}</div> : null}
    </div>
  );
}
