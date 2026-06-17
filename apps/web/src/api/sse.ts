import type { RunEvent } from "../types/contracts";
import { runApiPath } from "./paths";

export type RunEventConnectionState = "idle" | "connecting" | "open" | "error" | "closed";

export interface RunEventStreamOptions {
  runId: string;
  afterSeq?: number;
  onEvent: (event: RunEvent) => void;
  onConnectionChange?: (state: RunEventConnectionState) => void;
  onParseError?: (error: Error) => void;
}

export function openRunEventStream(options: RunEventStreamOptions): () => void {
  const search = new URLSearchParams();

  if (options.afterSeq) {
    search.set("after_seq", String(options.afterSeq));
  }

  const query = search.toString();
  const source = new EventSource(runApiPath(options.runId, `/events/stream${query ? `?${query}` : ""}`));

  options.onConnectionChange?.("connecting");

  source.addEventListener("open", () => {
    options.onConnectionChange?.("open");
  });

  source.addEventListener("run.event", (message) => {
    try {
      options.onEvent(JSON.parse(message.data) as RunEvent);
    } catch (error) {
      options.onParseError?.(error instanceof Error ? error : new Error("Unable to parse SSE event."));
    }
  });

  source.addEventListener("error", () => {
    options.onConnectionChange?.("error");
  });

  return () => {
    source.close();
    options.onConnectionChange?.("closed");
  };
}
