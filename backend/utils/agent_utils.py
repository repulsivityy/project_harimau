import asyncio
import functools
import json
import re
from langchain_core.messages import BaseMessage
from typing import List

INDICATOR_PATTERN = re.compile(
    r"^(?P<type>IP(?:\s*Address)?|Domain|URL|File|Hash|SHA256|MD5)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE
)


def parse_indicator_string(indicator: str) -> tuple:
    """Parse 'Type: value' indicator strings. Returns (entity_type, value) or (None, None)."""
    match = INDICATOR_PATTERN.match(indicator)
    if not match:
        return None, None
    ind_type_raw = match.group("type").strip().lower()
    ind_value = match.group("value").strip()
    if "ip" in ind_type_raw:
        return "ip_address", ind_value
    elif "domain" in ind_type_raw:
        return "domain", ind_value
    elif "url" in ind_type_raw:
        return "url", ind_value
    elif any(h in ind_type_raw for h in ["file", "hash", "sha", "md5"]):
        return "file", ind_value
    return None, ind_value


def build_peer_context(state: dict, iteration: int, self_agent: str, peer_agent: str,
                       extra_fields: list, count_key: str, logger) -> str:
    """Build peer specialist context string for injection into an agent prompt."""
    if iteration == 0:
        return ""
    peer_res = state.get("specialist_results", {}).get(peer_agent)
    if not peer_res:
        return ""

    lines = [f"\n**PEER SPECIALIST FINDINGS ({peer_agent.upper()}):**\n"]
    lines.append(f"- Verdict: {peer_res.get('verdict', 'Unknown')}\n")

    summary = peer_res.get("summary") or ""
    if len(summary) > 800:
        summary = summary[:800] + "..."
    lines.append(f"- Summary: {summary}\n")

    for label, key in extra_fields:
        if peer_res.get(key):
            lines.append(f"- {label}: {json.dumps(peer_res[key][:10])}\n")

    logger.info("peer_findings_injected", agent=self_agent, peer=peer_agent,
                count=len(peer_res.get(count_key, [])))

    return "".join(lines)

FINAL_ITERATION_PROMPT = (
    "This is the FINAL iteration. You MUST stop using tools now.\n\n"
    "Based on all the information you've gathered, prepare your comprehensive analysis. "
    "If you don't have enough information, provide your best analysis based on what "
    "you've gathered so far."
)


DEFAULT_TOOL_TIMEOUT = 20.0


def tool_timeout(seconds: float = DEFAULT_TOOL_TIMEOUT, logger=None):
    """
    Bound an agent tool coroutine with a wall-clock timeout and a catch-all.

    LangGraph's ToolNode has no timeout of its own; before the sub-graph refactor
    both this budget and the catch-all below were enforced by run_tools_parallel.
    Apply *under* @tool so the decorator still sees the original signature and
    docstring:

        @tool
        @tool_timeout()
        async def get_file_report(file_hash: str):
            ...

    Returns a JSON error string rather than raising, so the LLM sees a normal
    tool result. The catch-all matters because ToolNode's default
    handle_tool_errors (_default_handle_tool_errors) only converts
    ToolInvocationError into a message and re-raises everything else — which
    would abort the whole specialist. The tool bodies each have their own
    try/except around the MCP call, but their `await emit_tool_call(...)`
    transparency hop sits *outside* it, so an SSE failure (e.g. a browser tab
    closing mid-hunt) would otherwise escape and fail the hunt.

    CancelledError derives from BaseException, so genuine cancellation still
    propagates untouched.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                if logger:
                    logger.error("tool_timeout", tool=func.__name__, timeout=seconds)
                return json.dumps({"error": f"Tool {func.__name__} timed out after {seconds} seconds."})
            except Exception as e:
                if logger:
                    logger.error("tool_error", tool=func.__name__, error=str(e))
                return json.dumps({"error": f"Tool {func.__name__} failed - {str(e)}"})
        return wrapper
    return decorator


def reduce_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """LangGraph reducer: ID-based dedup merge with full-history overwrite support."""
    if right and right[0].additional_kwargs.get("overwrite_history"):
        return right
    merged = list(left)
    for msg in right:
        replaced = False
        if msg.id:
            for idx, existing in enumerate(merged):
                if existing.id == msg.id:
                    merged[idx] = msg
                    replaced = True
                    break
        if not replaced:
            merged.append(msg)
    return merged


def push_to_rich_intel(relationships_data: dict, rel_name: str, entity_type: str, value: str, source_id: str, attributes: dict = None) -> None:
    """
    Append an entity to relationships_data[rel_name], skipping exact duplicates
    (same id + same source_id).
    """
    if attributes is None:
        attributes = {}
    if rel_name not in relationships_data:
        relationships_data[rel_name] = []
        
    norm_val = str(value).strip().lower() if value else ""
    norm_src = str(source_id).strip().lower() if source_id else ""
    
    exists = any(
        str(e.get("id")).strip().lower() == norm_val and str(e.get("source_id")).strip().lower() == norm_src
        for e in relationships_data[rel_name]
    )
    if not exists:
        relationships_data[rel_name].append({
            "id": value,
            "type": entity_type,
            "source_id": source_id,
            "attributes": attributes,
        })
