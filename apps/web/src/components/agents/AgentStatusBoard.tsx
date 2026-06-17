import type { AgentExecution, ConsoleStatus } from "../../types/contracts";
import { AgentStatusPanel } from "./AgentStatusPanel";

interface AgentStatusBoardProps {
  agents: AgentExecution[];
  consoleStatus?: ConsoleStatus;
}

export function AgentStatusBoard({ agents, consoleStatus }: AgentStatusBoardProps) {
  return <AgentStatusPanel agents={agents} consoleStatus={consoleStatus} />;
}
