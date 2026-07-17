import asyncio
import json
import re
from langchain_core.messages import AIMessage, BaseMessage
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


async def run_tools_parallel(tool_dispatch: dict, tool_calls: list, agent_name: str, logger, timeout: float = 20.0) -> list:
    """
    Execute a batch of LLM tool calls in parallel, each with an individual timeout.
    Returns a list of result strings in the same order as tool_calls.
    """
    async def _run(tc):
        fn = tool_dispatch.get(tc["name"])
        if fn is None:
            logger.warning(f"{agent_name}_unknown_tool", tool=tc["name"])
            return f"Error: Tool {tc['name']} not found"
        try:
            return await asyncio.wait_for(fn.ainvoke(tc["args"]), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"{agent_name}_tool_timeout", tool=tc["name"])
            return f"Error: Tool {tc['name']} timed out after {timeout} seconds."
        except Exception as e:
            logger.error(f"{agent_name}_tool_error", tool=tc["name"], error=str(e))
            return f"Error: Tool {tc['name']} failed - {str(e)}"

    return list(await asyncio.gather(*[_run(tc) for tc in tool_calls]))


# def cap_context_window(messages: list, system_count: int = 2, tail_size: int = 10) -> list:
#     """
#     Prevent unbounded message growth during the agent loop.
# 
#     Keeps the first `system_count` messages (system prompt + initial task) and the
#     most recent `tail_size` messages. The tail is trimmed to start on an AIMessage
#     so no ToolMessage is left without its parent AIMessage, which the API rejects.
#     """
#     if len(messages) <= system_count + tail_size:
#         return messages
#     tail = messages[-tail_size:]
#     first_ai = next((i for i, m in enumerate(tail) if isinstance(m, AIMessage)), len(tail))
#     return messages[:system_count] + tail[first_ai:]


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
