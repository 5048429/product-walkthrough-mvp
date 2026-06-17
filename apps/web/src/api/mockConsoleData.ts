import { getMockAgentsForStatus, mockAgents } from "../mock/agents";
import { getMockEventsForStatus, mockEvents } from "../mock/events";
import { mockEvidence } from "../mock/evidence";
import { mockPlans } from "../mock/plans";
import { mockReport } from "../mock/report";
import { mockActiveRun, mockRecentRuns } from "../mock/runs";

export const mockConsoleData = {
  plans: mockPlans,
  activeRun: mockActiveRun,
  recentRuns: mockRecentRuns,
  agents: mockAgents,
  events: mockEvents,
  getAgentsForStatus: getMockAgentsForStatus,
  getEventsForStatus: getMockEventsForStatus,
  evidence: mockEvidence,
  report: mockReport,
};
