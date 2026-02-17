"""
Transparency event helpers for agent activity logging.

Provides utility functions to emit tool invocations and agent reasoning
to the SSE event stream for real-time frontend visibility.
"""

from typing import Dict, Any


async def emit_tool_call(job_id: str, agent: str, tool: str, args: Dict[str, Any]):
    """
    Emit a tool invocation event.
    
    Args:
        job_id: Investigation job ID
        agent: Agent name (e.g., "triage", "malware_specialist")
        tool: Tool function name
        args: Tool arguments
    """
    from backend.utils.sse_manager import sse_manager
    
    await sse_manager.emit_event(job_id, "tool_invocation", {
        "agent": agent,
        "tool": tool,
        "args": args
    })


async def emit_reasoning(job_id: str, agent: str, thought: str):
    """
    Emit an agent reasoning/thinking event.
    
    Args:
        job_id: Investigation job ID
        agent: Agent name
        thought: Agent's reasoning text (full LLM response content)
    """
    from backend.utils.sse_manager import sse_manager
    
    await sse_manager.emit_event(job_id, "agent_reasoning", {
        "agent": agent,
        "thought": thought
    })


async def emit_tool_result(job_id: str, agent: str, tool: str, result_summary: str):
    """
    Emit a tool result event (optional, for showing tool outputs).
    
    Args:
        job_id: Investigation job ID
        agent: Agent name
        tool: Tool function name
        result_summary: Brief summary of the result
    """
    from backend.utils.sse_manager import sse_manager
    
    await sse_manager.emit_event(job_id, "tool_result", {
        "agent": agent,
        "tool": tool,
        "result": result_summary
    })
