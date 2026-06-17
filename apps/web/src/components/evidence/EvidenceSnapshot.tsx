import { EvidenceList } from "./EvidenceList";
import type { Artifact, ConsoleStatus, EvidenceResponse } from "../../types/contracts";

interface EvidenceSnapshotProps {
  evidence: EvidenceResponse | null;
  artifacts?: Artifact[];
  status?: ConsoleStatus;
  error?: string | null;
  loading?: boolean;
}

export function EvidenceSnapshot({ evidence, artifacts, status, error, loading }: EvidenceSnapshotProps) {
  return <EvidenceList evidence={evidence} artifacts={artifacts} status={status} error={error} loading={loading} />;
}
