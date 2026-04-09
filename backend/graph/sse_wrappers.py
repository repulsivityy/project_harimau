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

            # Emit: Node started
            await sse_manager.emit_event(job_id, f"{node_name}_started", {
                "agent": node_name,
                "iteration": iteration,
                "message": f"{node_name.replace('_', ' ').title()} started",
                "progress": get_progress_estimate(node_name, "started", iteration, max_iterations)
            })

            try:
                # Execute the actual node (handle both sync and async)
                if asyncio.iscoroutinefunction(func):
                    result = await func(state)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, func, state)

                # Emit: Node completed
                await sse_manager.emit_event(job_id, f"{node_name}_completed", {
                    "agent": node_name,
                    "iteration": iteration,
                    "message": f"{node_name.replace('_', ' ').title()} completed",
                    "progress": get_progress_estimate(node_name, "completed", iteration, max_iterations)
                })

                return result

            except Exception as exc:
                # Emit: Node failed (so the frontend knows something went wrong)
                await sse_manager.emit_event(job_id, f"{node_name}_failed", {
                    "agent": node_name,
                    "iteration": iteration,
                    "message": f"{node_name.replace('_', ' ').title()} failed: {str(exc)[:200]}",
                    "progress": get_progress_estimate(node_name, "completed", iteration, max_iterations)
                })
                raise  # Re-raise so LangGraph sees the failure

        return async_wrapper

    return decorator


def get_progress_estimate(node_name: str, phase: str, iteration: int, max_iterations: int) -> int:
    """
    Estimate progress percentage based on node, phase, and iteration.

    Model:
      0-10%  : investigation_started → triage_started
      10%    : triage begins
      10-90% : split evenly across iterations (triage counts as iteration 0)
               each iteration has: specialists (first half) → lead_hunter (second half)
      90%    : lead_hunter begins final synthesis
      100%   : investigation_completed

    Within each iteration's band:
      - specialists_started  → band start
      - specialists_completed → band midpoint
      - lead_hunter_started  → band midpoint
      - lead_hunter_completed → band end
    """
    TRIAGE_START = 10
    SYNTHESIS_START = 90
    BAND = SYNTHESIS_START - TRIAGE_START  # 80 points spread across iterations

    # Triage is always 10%
    if node_name == "triage":
        return TRIAGE_START if phase == "started" else TRIAGE_START

    # Gate is a pass-through, keep progress where it was
    if node_name == "gate":
        return TRIAGE_START + int(BAND * iteration / max(max_iterations, 1))

    # Iteration band: each iteration gets an equal slice of the 10-90 range
    iters = max(max_iterations, 1)
    band_size = BAND / iters
    band_start = TRIAGE_START + band_size * iteration

    if node_name in ("malware_specialist", "infrastructure_specialist"):
        # Parallel agents share the first half of the iteration band
        if phase == "started":
            return int(band_start)
        return int(band_start + band_size * 0.5)

    if node_name == "lead_hunter":
        # Check if this is the final synthesis (iteration >= max_iterations)
        if iteration >= max_iterations:
            return SYNTHESIS_START if phase == "started" else 95
        # Otherwise it's a planning pass — second half of iteration band
        if phase == "started":
            return int(band_start + band_size * 0.5)
        return int(band_start + band_size)

    return 50  # Fallback
