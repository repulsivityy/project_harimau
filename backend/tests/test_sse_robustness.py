"""
Tests for S4-T4 (SSE error wrapping & dynamic progress).

1. SSEEventManager.emit_event must never raise to its caller, even when a
   subscriber's queue.put() fails, or when the subscriber list for a job_id
   is mutated out from under it mid-broadcast (the browser-tab-closed race
   between emit_event's iteration and subscribe()'s cleanup `finally` block).
2. with_sse_events must guard each of its three emits (started/completed/
   failed) individually: an emit failure must never stop the node from
   running, and must never mask a real node exception.
3. The transparency helpers (emit_tool_call/emit_reasoning/emit_tool_result)
   must swallow emit_event failures and return normally, since they're
   awaited from inside @tool bodies.
4. get_progress_estimate must be subtask-aware, monotone non-decreasing
   across a realistic full-hunt event sequence, bounded to [0, 100], and must
   no longer produce the 103% regression for specialists at
   iteration == max_iterations. SSEEventManager.emit_event must also enforce
   monotonicity centrally (clamp to at least the last emitted progress for
   that job_id), independent of what the curve itself produces.

Plain pytest, no pytest-asyncio dependency: coroutines are driven with
asyncio.run(...) inside ordinary sync test functions, following the style of
test_specialist_subgraph.py.
"""
import asyncio

from backend.utils.sse_manager import SSEEventManager, sse_manager
from backend.graph.sse_wrappers import with_sse_events, get_progress_estimate
from backend.utils import transparency


# ---------------------------------------------------------------------------
# Fake subscriber queues
# ---------------------------------------------------------------------------

class RaisingQueue:
    """A subscriber queue whose put() always raises (simulates a dead/closed
    consumer)."""
    async def put(self, event):
        raise RuntimeError("dead subscriber")


class RecordingQueue:
    """A healthy subscriber queue that records everything delivered to it."""
    def __init__(self):
        self.received = []

    async def put(self, event):
        self.received.append(event)


class DisconnectingQueue:
    """Simulates the real disconnect race: subscribe()'s `finally` block can
    delete self._subscribers[job_id] entirely (last subscriber leaving) while
    emit_event is broadcasting. This queue's put() reproduces that by
    deleting the manager's subscriber entry for job_id mid-broadcast."""
    def __init__(self, manager: SSEEventManager, job_id: str):
        self._manager = manager
        self._job_id = job_id

    async def put(self, event):
        if self._job_id in self._manager._subscribers:
            del self._manager._subscribers[self._job_id]


# ---------------------------------------------------------------------------
# 1. emit_event error containment
# ---------------------------------------------------------------------------

def test_emit_event_records_history_despite_raising_subscriber():
    manager = SSEEventManager()
    manager.create_queue("job-1")
    manager._subscribers["job-1"].append(RaisingQueue())

    # Must not raise.
    asyncio.run(manager.emit_event("job-1", "triage_started", {"message": "hi"}))

    events = manager.get_events("job-1")
    assert len(events) == 1
    assert events[0]["event_type"] == "triage_started"


def test_emit_event_raising_subscriber_does_not_block_healthy_subscriber():
    manager = SSEEventManager()
    manager.create_queue("job-2")
    healthy = RecordingQueue()
    manager._subscribers["job-2"].append(RaisingQueue())
    manager._subscribers["job-2"].append(healthy)

    asyncio.run(manager.emit_event("job-2", "triage_started", {"message": "hi"}))

    assert len(healthy.received) == 1
    assert healthy.received[0]["event_type"] == "triage_started"


def test_emit_event_survives_subscriber_list_mutation_mid_broadcast():
    manager = SSEEventManager()
    manager.create_queue("job-3")
    healthy = RecordingQueue()
    # DisconnectingQueue deletes manager._subscribers["job-3"] entirely when
    # its put() runs; a healthy queue is enqueued after it so we can also
    # confirm delivery continues for subscribers snapshotted earlier.
    manager._subscribers["job-3"].append(DisconnectingQueue(manager, "job-3"))
    manager._subscribers["job-3"].append(healthy)

    # Must not raise (RuntimeError: list changed size during iteration / KeyError).
    asyncio.run(manager.emit_event("job-3", "triage_completed", {"message": "bye"}))

    # The healthy subscriber, snapshotted before the mutation, still got the event.
    assert len(healthy.received) == 1
    # History is still recorded even though the live subscriber dict was wiped.
    events = manager.get_events("job-3")
    assert len(events) == 1


# ---------------------------------------------------------------------------
# 2. with_sse_events error containment
# ---------------------------------------------------------------------------

def _patch_emit_event(fn):
    """Monkeypatch sse_manager.emit_event for the duration of a block."""
    original = sse_manager.emit_event
    sse_manager.emit_event = fn
    return original


async def _raising_emit(job_id, event_type, data):
    raise RuntimeError("sse broadcast exploded")


def test_with_sse_events_runs_node_when_started_emit_raises():
    async def node_fn(state):
        return {"result": "ok", "iteration": state.get("iteration", 0)}

    wrapped = with_sse_events("unit_test_node")(node_fn)

    original = _patch_emit_event(_raising_emit)
    try:
        state = {"job_id": "job-4", "iteration": 0, "max_iterations": 1, "subtasks": []}
        result = asyncio.run(wrapped(state))
    finally:
        sse_manager.emit_event = original

    assert result == {"result": "ok", "iteration": 0}


def test_with_sse_events_node_exception_propagates_unmasked():
    class NodeBoom(ValueError):
        pass

    async def failing_node(state):
        raise NodeBoom("node exploded")

    wrapped = with_sse_events("unit_test_failing_node")(failing_node)

    original = _patch_emit_event(_raising_emit)
    try:
        try:
            asyncio.run(wrapped({"job_id": "job-5", "iteration": 0, "max_iterations": 1, "subtasks": []}))
            raise AssertionError("expected NodeBoom to propagate")
        except NodeBoom as exc:
            assert str(exc) == "node exploded"
    finally:
        sse_manager.emit_event = original


# ---------------------------------------------------------------------------
# 3. transparency helpers swallow emit_event failures
# ---------------------------------------------------------------------------

def test_transparency_helpers_return_normally_when_emit_event_raises():
    original = sse_manager.emit_event
    sse_manager.emit_event = _raising_emit
    try:
        asyncio.run(transparency.emit_tool_call("job-6", "malware_specialist", "get_file_report", {"file_hash": "a"}))
        asyncio.run(transparency.emit_reasoning("job-6", "malware_specialist", "thinking..."))
        asyncio.run(transparency.emit_tool_result("job-6", "malware_specialist", "get_file_report", "summary"))
    finally:
        sse_manager.emit_event = original


# ---------------------------------------------------------------------------
# 4. Progress estimate: subtask-aware, monotone, bounded
# ---------------------------------------------------------------------------

def _full_curve_sequence(max_iterations, subtask_count=3):
    """
    Realistic full-hunt sequence of (node_name, phase, iteration) triples,
    mirroring main.py's hardcoded anchors (workflow_started=5,
    investigation_completed=100) around the wrapped-node progression:

      triage started/completed
      per iteration 0..max_iterations: specialists started/completed,
        lead_hunter started/completed (the last iteration's lead_hunter pass
        is the final synthesis, since iteration == max_iterations there)
    """
    seq = [("triage", "started", 0), ("triage", "completed", 0)]
    for it in range(0, max_iterations + 1):
        seq.append(("malware_specialist", "started", it))
        seq.append(("malware_specialist", "completed", it))
        seq.append(("lead_hunter", "started", it))
        seq.append(("lead_hunter", "completed", it))
    return seq


def test_progress_curve_monotone_and_bounded_for_various_max_iterations():
    for max_it in (1, 2, 3, 5):
        values = [5]  # workflow_started anchor (main.py)
        for node, phase, it in _full_curve_sequence(max_it):
            values.append(get_progress_estimate(node, phase, it, max_it, subtask_count=3))
        values.append(100)  # investigation_completed anchor (main.py)

        assert all(0 <= v <= 100 for v in values), f"out of bounds for max_it={max_it}: {values}"
        for a, b in zip(values, values[1:]):
            assert a <= b, f"progress regression for max_it={max_it}: {a} -> {b} in {values}"


def test_specialists_at_final_iteration_never_reach_90():
    for max_it in (1, 2, 3, 5):
        started = get_progress_estimate("malware_specialist", "started", max_it, max_it, subtask_count=10)
        completed = get_progress_estimate("malware_specialist", "completed", max_it, max_it, subtask_count=10)
        assert started < 90, f"max_it={max_it}: started={started}"
        assert completed < 90, f"max_it={max_it}: completed={completed}"


def test_triage_completed_advances_past_started():
    started = get_progress_estimate("triage", "started", 0, 3)
    completed = get_progress_estimate("triage", "completed", 0, 3)
    assert completed > started


def test_progress_varies_with_subtask_count():
    low = get_progress_estimate("malware_specialist", "completed", 0, 3, subtask_count=1)
    high = get_progress_estimate("malware_specialist", "completed", 0, 3, subtask_count=10)
    assert high > low


def test_final_synthesis_exact_values():
    max_it = 3
    assert get_progress_estimate("lead_hunter", "started", max_it, max_it) == 90
    assert get_progress_estimate("lead_hunter", "completed", max_it, max_it) == 95


def test_progress_never_exceeds_100_or_goes_below_0():
    for max_it in (0, 1, 2, 3, 5, 10):
        for it in range(0, max_it + 2):
            for node in ("triage", "malware_specialist", "infrastructure_specialist", "lead_hunter", "gate"):
                for phase in ("started", "completed"):
                    v = get_progress_estimate(node, phase, it, max_it, subtask_count=7)
                    assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# 4b. Central, per-job monotone clamp in SSEEventManager.emit_event
# ---------------------------------------------------------------------------

def test_emit_event_central_clamp_over_realistic_sequence():
    manager = SSEEventManager()
    job_id = "job-7"
    max_it = 3

    recorded = []
    asyncio.run(manager.emit_event(job_id, "workflow_started", {"progress": 5}))
    recorded.append(manager.get_events(job_id)[-1]["data"]["progress"])

    for node, phase, it in _full_curve_sequence(max_it):
        progress = get_progress_estimate(node, phase, it, max_it, subtask_count=3)
        asyncio.run(manager.emit_event(job_id, f"{node}_{phase}", {"progress": progress}))
        recorded.append(manager.get_events(job_id)[-1]["data"]["progress"])

    asyncio.run(manager.emit_event(job_id, "investigation_completed", {"progress": 100}))
    recorded.append(manager.get_events(job_id)[-1]["data"]["progress"])

    assert all(0 <= v <= 100 for v in recorded)
    for a, b in zip(recorded, recorded[1:]):
        assert a <= b, f"clamp failed to enforce monotonicity: {recorded}"
    assert recorded[-1] == 100


def test_emit_event_clamp_forces_a_regression_upward():
    """Directly proves the clamp: feed a high progress value, then a lower
    one, and confirm the lower one is replaced by the previously-seen high."""
    manager = SSEEventManager()
    job_id = "job-8"

    asyncio.run(manager.emit_event(job_id, "lead_hunter_started", {"progress": 90}))
    asyncio.run(manager.emit_event(job_id, "malware_specialist_started", {"progress": 40}))

    events = manager.get_events(job_id)
    assert events[0]["data"]["progress"] == 90
    # The stray lower value must be clamped up to the last emitted progress.
    assert events[1]["data"]["progress"] == 90


def test_investigation_completed_still_emits_100_after_clamp():
    manager = SSEEventManager()
    job_id = "job-9"

    asyncio.run(manager.emit_event(job_id, "lead_hunter_completed", {"progress": 95}))
    asyncio.run(manager.emit_event(job_id, "investigation_completed", {"progress": 100}))

    events = manager.get_events(job_id)
    assert events[-1]["data"]["progress"] == 100


def test_clear_history_resets_progress_clamp():
    manager = SSEEventManager()
    job_id = "job-10"

    asyncio.run(manager.emit_event(job_id, "lead_hunter_completed", {"progress": 95}))
    manager.clear_history(job_id)
    assert job_id not in manager._last_progress

    # A fresh run of the same job_id must not be clamped up by the stale 95
    # from the previous run — the clamp's "last" for this job_id is gone.
    asyncio.run(manager.emit_event(job_id, "workflow_started", {"progress": 5}))
    assert manager._last_progress[job_id] == 5


# ---------------------------------------------------------------------------
# Gaps found in review of this suite — the assertions that actually pin the
# two fixes the tests above only appeared to cover.
# ---------------------------------------------------------------------------

class RemovingQueue:
    """
    The genuine list-mutation case: subscribe()'s `finally` removes *this*
    queue from the list (list.remove) rather than deleting the whole job entry.
    Against an unsnapshotted broadcast loop this silently shortens the list
    mid-iteration and later subscribers are skipped — no exception, just lost
    events. Measured pre-fix: 1 of 3 delivered.
    """
    def __init__(self, manager: SSEEventManager, job_id: str):
        self._manager = manager
        self._job_id = job_id

    async def put(self, event):
        queues = self._manager._subscribers.get(self._job_id)
        if queues and self in queues:
            queues.remove(self)


def test_emit_event_still_delivers_to_all_after_list_remove_mid_broadcast():
    manager = SSEEventManager()
    manager.create_queue("job-remove")
    first = RecordingQueue()
    second = RecordingQueue()
    # The removing queue sits between two healthy ones, so an unsnapshotted
    # loop would shift indices and skip `second` entirely.
    manager._subscribers["job-remove"].append(first)
    manager._subscribers["job-remove"].append(RemovingQueue(manager, "job-remove"))
    manager._subscribers["job-remove"].append(second)

    asyncio.run(manager.emit_event("job-remove", "triage_started", {"message": "hi"}))

    assert len(first.received) == 1
    assert len(second.received) == 1, "subscriber after the removed one was skipped"


def test_failed_emit_does_not_mask_the_node_exception():
    """
    The specific fix the existing propagation test misses: that test makes the
    _started emit raise, so it fails before the node ever runs and never
    exercises the _failed handler. Here only the _failed emit raises, which is
    what used to replace the real node error with the emit's own.
    """
    class NodeBoom(Exception):
        pass

    async def failing_node(state):
        raise NodeBoom("node exploded")

    async def emit_only_failed_raises(job_id, event_type, data):
        if event_type.endswith("_failed"):
            raise RuntimeError("failed-emit exploded")

    wrapped = with_sse_events("unit_test_node")(failing_node)

    original = _patch_emit_event(emit_only_failed_raises)
    try:
        raised = None
        try:
            asyncio.run(wrapped({"job_id": "job-mask", "iteration": 0, "max_iterations": 1}))
        except Exception as exc:
            raised = exc
    finally:
        sse_manager.emit_event = original

    assert isinstance(raised, NodeBoom), f"node exception was masked by {type(raised).__name__}"
    assert "node exploded" in str(raised)
    # The emit's own error must not even be chained in as the active context.
    assert not isinstance(raised.__context__, RuntimeError)


def test_sync_node_path_survives_all_emits_failing():
    """
    The run_in_executor branch for non-coroutine nodes was untested. A sync
    node must still run and return, and a sync node's exception must still
    propagate with its original type.
    """
    def sync_node(state):
        return {"ok": True}

    def sync_boom(state):
        raise KeyError("sync exploded")

    original = _patch_emit_event(_raising_emit)
    try:
        result = asyncio.run(
            with_sse_events("unit_test_node")(sync_node)(
                {"job_id": "job-sync", "iteration": 0, "max_iterations": 1}
            )
        )
        assert result == {"ok": True}

        raised = None
        try:
            asyncio.run(
                with_sse_events("unit_test_node")(sync_boom)(
                    {"job_id": "job-sync2", "iteration": 0, "max_iterations": 1}
                )
            )
        except Exception as exc:
            raised = exc
        assert isinstance(raised, KeyError)
    finally:
        sse_manager.emit_event = original


def test_subtask_count_is_robust_to_a_non_sized_subtasks_value():
    """
    subtask_count is computed before the guarded _started emit and outside the
    node's try, so a non-sized `subtasks` would abort the node before it ran.
    """
    async def node_fn(state):
        return {"ran": True}

    wrapped = with_sse_events("unit_test_node")(node_fn)
    result = asyncio.run(wrapped({
        "job_id": "job-badsubtasks",
        "iteration": 0,
        "max_iterations": 1,
        "subtasks": 7,  # not a list
    }))
    assert result == {"ran": True}
