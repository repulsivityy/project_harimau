# Debugging & Fix: Graph Node Limit (Jan 23, 2026)

## Problem Description
The frontend graph was only ensuring one node per relationship (e.g., 1 `memory_pattern_url` instead of 9), despite `MAX_ENTITIES_PER_RELATIONSHIP` being set to a higher value.

### Symptoms
- Graph visualization showed sparse connections.
- Users reported "missing data" in the visual graph.
- Logs showed `count=1` for entities that should have had multiple items.

## Root Cause Analysis
1.  **Initial Hypothesis**: `MAX_ENTITIES_PER_RELATIONSHIP` limit in `triage.py`. (Disproven: Limit was 10, data was 9).
2.  **Second Hypothesis**: VirusTotal API pagination using `batch_size=0`. (Disproven: Local tests showed correct data fetching).
3.  **Final Diagnosis**: **FastMCP Serialization Bug**.
    - When an MCP tool returns a raw `list` (e.g., `[...]`), the FastMCP server implementation (or Pydantic validation layer involved in JSON-RPC) was inadvertently truncating or mishandling the list, resulting in the client receiving only the *first item* as a single object or a list of one.
    - Verified by server logs: Server logged `Returning 9 items`, but client received `1`.

## The Fix
We implemented a workaround by wrapping the list response in a dictionary. This forces FastMCP to treat the return value as a single object (the dict), preserving the inner list structure.

**Old Return Format:**
```python
# Server
return [entity1, entity2, ...] 
# Client received: entity1 (or [entity1])
```

**New Return Format:**
```python
# Server
return {"data": [entity1, entity2, ...]}
# Client received: {"data": [entity1, entity2, ...]}
```

### Files Modified
1.  `backend/mcp/gti/tools/files.py`: Updated `get_entities_related_to_a_file`.
2.  `backend/mcp/gti/tools/netloc.py`: Updated `get_entities_related_to_a_domain` and `get_entities_related_to_an_ip_address`.
3.  `backend/mcp/gti/tools/urls.py`: Updated `get_entities_related_to_an_url`.

The `triage.py` agent was already equipped to handle `{"data": ...}` wrapped responses (from `parse_mcp_tool_response`), so no client-side changes were strictly necessary for the fix to work, though we did update `triage.py` previously to improve parsing robustness.

## Verification
1.  **Deployment**: Deployed backend revision `harimau-backend-00058`.
2.  **Test Case**: File Hash `ef3103d84953226cfb965888a4e71b2173b9798599db27af8653918502cbde8f`.
3.  **Result**: 
    - Graph now correctly displays ~9 `memory_pattern_urls` nodes.
    - Debug logs show `parse_mcp_format` returning `wrapped_array` with correct counts.

## Lessons Learned
- **FastMCP List Handling**: Be cautious when returning root-level lists from FastMCP tools. Wrapping in a dictionary is a safer pattern for complex objects.
- **Traceability**: Adding `[DEBUG]` logs to the MCP server was crucial to isolate the issue to the transmission layer (Server sent 9, Client got 1).
