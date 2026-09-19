import assert from "node:assert/strict";
import test from "node:test";

import {
  reconcileTerminalInvestigationEvent,
  terminalStatusFromInvestigationEvent,
} from "../src/lib/investigation-stream";

test("a terminal SSE snapshot is authoritative and carries its saved timeline", () => {
  const subtasks = [{ agent: "triage", status: "completed" }];
  const transparencyLog = [{ type: "tool", agent: "triage" }];

  const update = reconcileTerminalInvestigationEvent("investigation_snapshot", {
    status: "cancelled",
    terminal: true,
    subtasks,
    transparency_log: transparencyLog,
  });

  assert.deepEqual(update, {
    status: "cancelled",
    progress: 100,
    message: "Mission cancelled.",
    subtasks,
    transparencyLog,
  });
});

test("terminal event type wins over a stale payload status", () => {
  assert.equal(
    terminalStatusFromInvestigationEvent("investigation_failed", {
      status: "running",
    }),
    "failed",
  );
});

test("live snapshots and ordinary agent events remain non-terminal", () => {
  assert.equal(
    reconcileTerminalInvestigationEvent("investigation_snapshot", {
      status: "running",
      terminal: false,
    }),
    null,
  );
  assert.equal(
    reconcileTerminalInvestigationEvent("triage_completed", {}),
    null,
  );
});
