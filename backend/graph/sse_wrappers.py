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
    
    Handles both sync and async nodes by converting everything to async.
    Sync nodes are run in executor to avoid blocking the event loop.
    
    Args:
        node_name: Name of the node (e.g., 'triage', 'malware_specialist')
    
    Usage:
        @with_sse_events('triage')
        def triage_node(state: AgentState) -> AgentState:
            ...
    """
    def decorator(func: Callable[[AgentState], AgentState]):
        @wraps(func)
        async def async_wrapper(state: AgentState) -> AgentState:
            job_id = state.get("job_id")
            iteration = state.get("iteration", 0)
            
            # Emit: Node started
            await sse_manager.emit_event(job_id, f"{node_name}_started", {
                "agent": node_name,
                "iteration": iteration,
                "message": f"{node_name.replace('_', ' ').title()} started",
                "progress": get_progress_estimate(node_name, "started", iteration)
            })
            
            # Execute the actual node (handle both sync and async)
            if asyncio.iscoroutinefunction(func):
                result = await func(state)
            else:
                # Run sync function in executor to avoid blocking event loop
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, func, state)
            
            # Emit: Node completed
            await sse_manager.emit_event(job_id, f"{node_name}_completed", {
                "agent": node_name,
                "iteration": iteration,
                "message": f"{node_name.replace('_', ' ').title()} completed",
                "progress": get_progress_estimate(node_name, "completed", iteration)
            })
            
            return result
        
        return async_wrapper
    
    return decorator


def get_progress_estimate(node_name: str, phase: str, iteration: int) -> int:
    """
    Estimate progress percentage based on node and iteration.
    
    Workflow timeline (single iteration):
    - investigation_started: 0%
    - triage_started: 5%
    - triage_completed: 20%
    - malware_specialist_started: 25%
    - malware_specialist_completed: 50%
    - infrastructure_specialist_started: 55%
    - infrastructure_specialist_completed: 80%
    - lead_hunter_started: 85%
    - lead_hunter_completed: 95%
    - investigation_completed: 100%
    """
    # Base progress map for iteration 0
    progress_map = {
        "triage": {"started": 5, "completed": 20},
        "gate": {"started": 22, "completed": 24},
        "malware_specialist": {"started": 25, "completed": 50},
        "infrastructure_specialist": {"started": 55, "completed": 80},
        "lead_hunter": {"started": 85, "completed": 95},
    }
    
    base_progress = progress_map.get(node_name, {}).get(phase, 0)
    
    # Adjust for iterations (each iteration is worth less)
    if iteration > 0:
        # Subsequent iterations take us from 95% → 100%
        iteration_boost = min(iteration * 2, 5)
        return min(base_progress + iteration_boost, 98)  # Cap at 98%, reserve 100 for completion
    
    return base_progress
