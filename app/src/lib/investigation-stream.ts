/**
 * Normalisation shared by the investigation page's SSE and REST paths.
 *
 * The backend always opens an SSE stream with an `investigation_snapshot`.
 * Event history is deliberately ephemeral, so a terminal snapshot is the
 * durable authority after reconnecting to a completed, failed, or cancelled
 * investigation.
 */

export const TERMINAL_INVESTIGATION_STATUSES = [
  "completed",
  "failed",
  "cancelled",
] as const;

export type TerminalInvestigationStatus =
  (typeof TERMINAL_INVESTIGATION_STATUSES)[number];

export type InvestigationStreamData = Record<string, unknown>;

export interface TerminalInvestigationUpdate {
  status: TerminalInvestigationStatus;
  progress: 100;
  message: string;
  subtasks?: unknown[];
  transparencyLog?: unknown[];
}

function terminalStatus(value: unknown): TerminalInvestigationStatus | null {
  if (typeof value !== "string") return null;

  const status = value.toLowerCase();
  return TERMINAL_INVESTIGATION_STATUSES.includes(
    status as TerminalInvestigationStatus,
  )
    ? (status as TerminalInvestigationStatus)
    : null;
}

/** Return the terminal status implied by an event, if it has one. */
export function terminalStatusFromInvestigationEvent(
  eventType: unknown,
  data: InvestigationStreamData,
): TerminalInvestigationStatus | null {
  switch (eventType) {
    case "investigation_completed":
      return "completed";
    case "investigation_failed":
      return "failed";
    case "investigation_cancelled":
      return "cancelled";
    case "investigation_snapshot":
      // A snapshot is durable state, unlike the process-local event history.
      // Its terminal status wins even if an older queued event follows it.
      return terminalStatus(data.status);
    default:
      return null;
  }
}

function terminalMessage(
  status: TerminalInvestigationStatus,
  data: InvestigationStreamData,
): string {
  if (status === "completed") return "Mission complete.";
  if (status === "cancelled") return "Mission cancelled.";

  const error = typeof data.error === "string" && data.error.trim()
    ? data.error
    : "ERR_UNKNOWN";
  return `Mission failure: ${error}`;
}

/**
 * Produce the state update for a terminal SSE event or snapshot.
 *
 * Snapshot subtasks and transparency entries are intentionally included: they
 * let a reconnect render a terminal timeline before the REST detail fetch
 * returns. Non-terminal events return null and remain ordinary live updates.
 */
export function reconcileTerminalInvestigationEvent(
  eventType: unknown,
  data: InvestigationStreamData,
): TerminalInvestigationUpdate | null {
  const status = terminalStatusFromInvestigationEvent(eventType, data);
  if (!status) return null;

  return {
    status,
    progress: 100,
    message: terminalMessage(status, data),
    subtasks: Array.isArray(data.subtasks) ? data.subtasks : undefined,
    transparencyLog: Array.isArray(data.transparency_log)
      ? data.transparency_log
      : undefined,
  };
}

export function isTerminalInvestigationStatus(
  status: unknown,
): status is TerminalInvestigationStatus {
  return terminalStatus(status) !== null;
}
