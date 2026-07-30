"""
Node wrapper utilities for emitting SSE events during LangGraph execution.
"""

import asyncio
from functools import wraps
from typing import Callable
from backend.graph.state import AgentState
from backend.utils.sse_manager import sse_manager
from backend.utils.logger import get_logger

logger = get_logger("workflow-sse")


def with_sse_events(node_name: str):
    """
    Decorator to wrap LangGraph nodes with SSE event emissions.

    Emits _started before the node runs and _completed or _failed after.
    """
    def decorator(func: Callable[[AgentState], AgentState]):
        @wraps(func)
        async def async_wrapper(state: AgentState) -> AgentState:
            job_id = state.get("job_id")
            iteration = state.get("iteration", 0)
            max_iterations = state.get("max_iterations", 1)
            # Defensive len(): this runs before the guarded _started emit and
            # outside the node's own try, so a non-sized `subtasks` here would
            # abort the node before it ever ran — exactly the failure class the
            # rest of this wrapper exists to prevent.
            subtasks = state.get("subtasks")
            subtask_count = len(subtasks) if isinstance(subtasks, (list, tuple)) else 0

            # Emit: Node started. Guarded individually so a broadcast failure
            # here (e.g. a dead subscriber) can never stop the node from
            # running at all.
            logger.info("node_started", node=node_name, job_id=job_id, iteration=iteration)
            try:
                await sse_manager.emit_event(job_id, f"{node_name}_started", {
                    "agent": node_name,
                    "iteration": iteration,
                    "message": f"{node_name.replace('_', ' ').title()} started",
                    "progress": get_progress_estimate(node_name, "started", iteration, max_iterations, subtask_count)
                })
            except Exception as emit_exc:
                logger.error("sse_emit_failed", node=node_name, job_id=job_id, phase="started", error=str(emit_exc))

            try:
                # Execute the actual node (handle both sync and async)
                if asyncio.iscoroutinefunction(func):
                    result = await func(state)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, func, state)

                # Emit: Node completed
                logger.info("node_completed", node=node_name, job_id=job_id, iteration=iteration)
                try:
                    await sse_manager.emit_event(job_id, f"{node_name}_completed", {
                        "agent": node_name,
                        "iteration": iteration,
                        "message": f"{node_name.replace('_', ' ').title()} completed",
                        "progress": get_progress_estimate(node_name, "completed", iteration, max_iterations, subtask_count)
                    })
                except Exception as emit_exc:
                    logger.error("sse_emit_failed", node=node_name, job_id=job_id, phase="completed", error=str(emit_exc))

                return result

            except Exception as exc:
                # Emit: Node failed (so the frontend knows something went wrong).
                # This emit must never mask the original node exception below.
                logger.error("node_failed", node=node_name, job_id=job_id, iteration=iteration, error=str(exc))
                try:
                    await sse_manager.emit_event(job_id, f"{node_name}_failed", {
                        "agent": node_name,
                        "iteration": iteration,
                        "message": f"{node_name.replace('_', ' ').title()} failed: {str(exc)[:200]}",
                        "progress": get_progress_estimate(node_name, "completed", iteration, max_iterations, subtask_count)
                    })
                except Exception as emit_exc:
                    logger.error("sse_emit_failed", node=node_name, job_id=job_id, phase="failed", error=str(emit_exc))
                raise  # Re-raise so LangGraph sees the failure

        return async_wrapper

    return decorator


def get_progress_estimate(node_name: str, phase: str, iteration: int, max_iterations: int,
                           subtask_count: int = 0) -> int:
    """
    Estimate progress percentage based on node, phase, iteration, and how much
    work the current iteration actually has (subtask_count).

    Fixed anchors (kept in sync with the hardcoded emits in main.py):
      5%       : workflow_started
      100%     : investigation_completed

    Model:
      10-15%   : triage started -> completed
      15-90%   : split across `max_iterations + 1` specialist passes
                 (iterations 0..max_iterations — see the walkthrough in
                 sse_wrappers's caller / the S4-T4 brief: state["iteration"]
                 is only incremented by lead_hunter, so triage and the first
                 specialist pass both run at iteration 0, and there are
                 max_iterations+1 specialist passes, not max_iterations).
      90-95%   : final synthesis (lead_hunter with iteration >= max_iterations)

    Within an iteration's band, the specialist portion is weighted by
    subtask_count: more subtasks -> specialists occupy more of the band
    before lead_hunter's planning pass takes over.

    INVARIANT this relies on: within one iteration, the specialists and
    lead_hunter must see the same subtask_count. They do today because
    `subtasks` uses the `last_value` reducer and only triage and lead_hunter
    ever write it, so specialists leave it untouched. If a specialist ever
    starts returning "subtasks", the raw curve can regress mid-band (e.g.
    max_iterations=1 with specialists seeing 10 subtasks and lead_hunter 0
    yields 15, 45, 34, 52) and ordering would then be preserved only by
    sse_manager's central per-job clamp.

    Every non-terminal (pre-synthesis) value is clamped to at most
    SYNTHESIS_START - 1 so nothing can prematurely claim 90%+; the function
    never returns below 0 or above 100.
    """
    TRIAGE_START = 10
    TRIAGE_END = 15
    SYNTHESIS_START = 90
    SYNTHESIS_END = 95
    NON_TERMINAL_CAP = SYNTHESIS_START - 1  # 89

    def _clamp(value: float, upper: int = 100) -> int:
        return max(0, min(upper, int(round(value))))

    # Triage is the first band: started at 10%, completed advances to 15%.
    if node_name == "triage":
        return _clamp(TRIAGE_END if phase == "completed" else TRIAGE_START, NON_TERMINAL_CAP)

    max_iterations = max(max_iterations, 0)
    bands = max_iterations + 1  # max_iterations+1 specialist passes (see above)
    band = (SYNTHESIS_START - TRIAGE_END) / bands
    clamped_iteration = min(max(iteration, 0), bands - 1)
    start = TRIAGE_END + band * clamped_iteration

    # Gate is a pass-through node — kept here for completeness, but
    # workflow.py registers the raw gate_node unwrapped (with_sse_events is
    # never applied to it), so this branch is currently unreachable in
    # production.
    if node_name == "gate":
        return _clamp(start, NON_TERMINAL_CAP)

    # Weight specialists' share of the band by how much work this iteration
    # has. subtask_count == 0 means "no information yet", not "no work" —
    # use the neutral 0.5 split in that case rather than collapsing the band.
    if subtask_count <= 0:
        w = 0.5
    else:
        w = 0.4 + 0.4 * min(subtask_count, 10) / 10  # -> [0.4, 0.8]

    if node_name in ("malware_specialist", "infrastructure_specialist"):
        if phase == "started":
            return _clamp(start, NON_TERMINAL_CAP)
        return _clamp(start + band * w, NON_TERMINAL_CAP)

    if node_name == "lead_hunter":
        # Final synthesis (iteration >= max_iterations).
        #
        # NOTE: lead_hunter can also enter synthesis mode on an *early exit*
        # (no uninvestigated nodes, LLM signals complete, or convergence
        # detected — lead_hunter.py:78-100) while iteration < max_iterations.
        # This wrapper can't know that before the node runs, so such a hunt
        # reports a mid-band planning percentage here and then jumps straight
        # to 100 on investigation_completed. Documented, not fixed.
        if iteration >= max_iterations:
            return SYNTHESIS_START if phase == "started" else SYNTHESIS_END
        # Otherwise it's a planning pass — the remainder of the iteration band.
        if phase == "started":
            return _clamp(start + band * w, NON_TERMINAL_CAP)
        return _clamp(start + band, NON_TERMINAL_CAP)

    return 50  # Fallback
