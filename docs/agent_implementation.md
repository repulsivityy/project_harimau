# Agent Implementation Reference

*Supplement to [architecture.md](./architecture.md) - Last updated: 2026-02-07*

This document provides implementation-level details for the Harimau specialist agents.

---

## Agent Structure Pattern

Both Malware and Infrastructure specialists follow this proven pattern:

### Phase 1: Initialization
```python
async def specialist_node(state: AgentState):
    cache = state.get("investigation_graph")
    subtask = next((t for t in state.get("subtasks", []) 
                   if t.get("agent") == "specialist_name"), None)
    
    # Extract target or use regex fallback
    target = subtask.get("entity_id") or extract_from_task_text(subtask["task"])
```

### Phase 2: Tool Definition
```python
async with mcp_manager.get_session("gti") as session:
    @tool
    async def get_resource(identifier: str):
        """Tool description for LLM."""
        try:
            res = await session.call_tool("mcp_name", arguments={"param": identifier})
            return res.content[0].text if res.content else "{}"
        except Exception as e:
            return str(e)
```

### Phase 3: Agent Loop (10 Iterations)
```python
    llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0)
    llm_with_tools = llm.bind_tools([tool1, tool2, ...])

    messages = [SystemMessage(content=PROMPT), HumanMessage(content=task)]
    final_content = None
    max_iterations = malware_iterations  # or infra_iterations = 10

    for iteration in range(max_iterations):
        if iteration == max_iterations - 1:
            messages.append(HumanMessage(
                content="Final iteration. Provide comprehensive JSON structure."
            ))
        
        response = await llm.ainvoke(messages)
        messages.append(response)
        
        if response.tool_calls:
            for tc in response.tool_calls:
                tool_result = await tools[tc["name"]].ainvoke(tc["args"])
                messages.append(ToolMessage(content=tool_result, tool_call_id=tc["id"]))
        else:
            final_content = response.content
            if final_content: break
```

### Phase 4: Fallback Content Capture
```python
    # If loop exits without clean break
    if not final_content and messages:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                final_content = msg.content
                break
```

### Phase 5: JSON Parsing (Flexible)
```python
    result = parse_json_flexible(final_content)
```

### Phase 6: Report Generation
```python
    result["markdown_report"] = generate_specialist_markdown_report(result, ioc)
```

### Phase 7: State Updates
```python
    # Store results
    if "specialist_results" not in state:
        state["specialist_results"] = {}
    state["specialist_results"]["specialist_name"] = result
    
    # Update graph
    sync_findings_to_graph(state, result, target)
    
    # Mark subtask complete
    for task in state.get("subtasks", []):
        if task.get("agent") == "specialist_name":
            task["status"] = "completed"
            task["result_summary"] = result.get("summary")
    
    return state
```

---

## JSON Parsing Implementation

### Dual-Format Handler

Handles both `{...}` objects and `[{...}]` arrays:

```python
def parse_json_flexible(content: str) -> dict:
    # Remove markdown wrapping
    clean = content
    if "```json" in clean:
        clean = clean.split("```json")[-1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].strip() if clean.count("```") >= 2 else clean
    
    # Detect structure type
    array_start = clean.find("[")
    object_start = clean.find("{")
    
    if array_start != -1 and (object_start == -1 or array_start < object_start):
        # JSON Array: [{...}, {...}]
        end_idx = clean.rfind("]")
        if end_idx != -1:
            clean = clean[array_start:end_idx+1]
            parsed = json.loads(clean)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed[0]  # Take first element
            raise ValueError("Empty or invalid array")
        raise ValueError("No closing bracket found")
    
    elif object_start != -1:
        # JSON Object: {...}
        end_idx = clean.rfind("}")
        if end_idx != -1:
            clean = clean[object_start:end_idx+1]
            return json.loads(clean)
        raise ValueError("No closing brace found")
    
    else:
        raise ValueError(f"No JSON structure found. Content: {content[:100]}")
```

---

## MCP Tool Integration

### Argument Mapping Table

**Critical**: All three layers must use consistent parameter names.

| Entity | Python Function | MCP Tool Call |
|--------|----------------|---------------|
| IP Address | `async def get_ip_address_report(ip_address: str)` | `session.call_tool("get_ip_address_report", arguments={"ip_address": ip_address})` |
| Domain | `async def get_domain_report(domain: str)` | `session.call_tool("get_domain_report", arguments={"domain": domain})` |
| URL | `async def get_url_report(url: str)` | `session.call_tool("get_url_report", arguments={"url": url})` |
| File Hash | `async def get_file_report(file_hash: str)` | `session.call_tool("get_file_report", arguments={"resource": file_hash})` |

### Tool Definition Template

```python
@tool
async def get_ip_address_report(ip_address: str):
    """
    Get threat intelligence report for an IP address.
    
    Args:
        ip_address: The IP address to analyze (e.g., "8.8.8.8")
    
    Returns:
        JSON string with threat data or error message
    """
    try:
        res = await session.call_tool(
            "get_ip_address_report",
            arguments={"ip_address": ip_address}  # ✅ Must match MCP expectation
        )
        return res.content[0].text if res.content else "{}"
    except Exception as e:
        logger.warning("tool_error", tool="get_ip_address_report", error=str(e))
        return str(e)
```

---

## Error Handling Strategy

### Three-Layer Approach

1. **Tool Layer** (Graceful Degradation)
   ```python
   except Exception as e:
       return str(e)  # Return error as string, let agent decide
   ```

2. **Parsing Layer** (Detailed Context)
   ```python
   except Exception as e:
       state["specialist_results"]["agent"] = {
           "verdict": "System Error",
           "summary": f"Failed to parse analysis: {str(e)}",
           "markdown_report": f"""
## Analysis Failed

**Error Details:**
```
{str(e)}
```

**Raw LLM Output (first 2000 chars):**
```
{str(final_text)[:2000]}
```
"""
       }
   ```

3. **Node Layer** (Fatal Catchall)
   ```python
   except Exception as e:
       logger.error("fatal_agent_error", agent="specialist", error=str(e))
       import traceback
       state["specialist_results"]["agent"] = {
           "verdict": "System Error",
           "summary": f"Fatal error: {str(e)}",
           "markdown_report": f"""
## System Error

### Error
```
{str(e)}
```

### Traceback
```
{traceback.format_exc()}
```
"""
       }
```

---

## Configuration Constants

```python
# Malware Agent Configuration (Feb 2026)
malware_iterations = 10  # LLM analysis loop iterations
max_analysis_targets = 5  # File hash limit (prevents timeouts)

# Infrastructure Agent Configuration (Feb 2026)
infra_iterations = 10  # LLM analysis loop iterations
unique_targets_limit = 10  # Maximum entities to investigate per iteration

# LLM Settings
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0  # Deterministic analysis

# Error Display
ERROR_CONTEXT_CHARS = 2000  # Show 2000 chars of raw output on failure
```

---

## Deployment Considerations

### ❌ Avoid These Patterns

1. **Pydantic BaseModel schemas** in tool definitions
   - Causes serialization issues in Cloud Run
   - Use simple type hints instead

2. **Hardcoded `ip` parameter** in MCP calls
   - Must use `ip_address` to match server expectations

3. **Single-format JSON parsing**
   - LLM may return arrays or objects unpredictably

### ✅ Recommended Patterns

1. **Simple function signatures** with `@tool` decorator
2. **Consistent parameter naming** across all layers
3. **Flexible JSON parsing** with format detection
4. **Comprehensive error context** for debugging
5. **Fallback message capture** for interrupted loops

---

## Testing Checklist

Before deployment:

- [ ] Syntax validation: `python3 -m py_compile backend/agents/*.py`
- [ ] MCP argument names match across all tools
- [ ] JSON parsing handles both object and array formats
- [ ] Fallback logic present (and not duplicated)
- [ ] Error messages show 2000 chars context
- [ ] Subtask status updates implemented
- [ ] Graph sync logic includes `source_id`
- [ ] All imports present (ChatVertexAI, tool, etc.)

---

## Malware Specialist Tools (Feb 2026)

The Malware agent has access to 4 GTI tools via MCP:

1. **get_file_behavior** - Fetches sandbox behavior summary
   ```python
   @tool
   async def get_file_behavior(file_hash: str):
       res = await session.call_tool("get_file_behavior_summary", arguments={"hash": file_hash})
   ```

2. **get_dropped_files** - Files dropped during execution
   ```python
   @tool
   async def get_dropped_files(file_hash: str):
       res = await session.call_tool("get_entities_related_to_a_file", arguments={
           "hash": file_hash,
           "relationship_name": "dropped_files",
           "descriptors_only": True
       })
   ```

3. **get_attribution** - Malware families, threat actors, **and vulnerabilities**
   ```python
   @tool
   async def get_attribution(file_hash: str):
       # Fetches: malware_families, related_threat_actors, vulnerabilities
       # Returns JSON with all three relationship types
   ```

4. **get_file_report** - Full static analysis report (Added Feb 2026)
   ```python
   @tool
   async def get_file_report(file_hash: str):
       res = await session.call_tool("get_file_report", arguments={"file_hash": file_hash})
   ```

**Tool Binding:**
```python
llm.bind_tools([get_file_behavior, get_dropped_files, get_attribution, get_file_report])
```

---

## Infrastructure Specialist Tools

The Infrastructure agent has access to 7 GTI/WebRisk tools via MCP:

1. **get_domain_report** - Full threat intelligence report for a domain
   ```python
   @tool
   async def get_domain_report(domain: str):
       res = await session.call_tool("get_domain_report", arguments={"domain": domain})
   ```

2. **get_entities_related_to_a_domain** - Fetch related entities for a domain (resolutions, subdomains, communicating files, etc.)
   ```python
   @tool
   async def get_entities_related_to_a_domain(domain: str, relationship: str):
       res = await session.call_tool("get_entities_related_to_a_domain", arguments={
           "domain": domain, "relationship_name": relationship
       })
   ```

3. **get_ip_address_report** - Full threat intelligence report for an IP address
   ```python
   @tool
   async def get_ip_address_report(ip_address: str):
       res = await session.call_tool("get_ip_address_report", arguments={"ip_address": ip_address})
   ```

4. **get_entities_related_to_an_ip_address** - Fetch related entities for an IP (communicating files, resolutions, etc.)
   ```python
   @tool
   async def get_entities_related_to_an_ip_address(ip_address: str, relationship: str):
       res = await session.call_tool("get_entities_related_to_an_ip_address", arguments={
           "ip_address": ip_address, "relationship_name": relationship
       })
   ```

5. **get_url_report** - Full threat intelligence report for a URL
   ```python
   @tool
   async def get_url_report(url: str):
       res = await session.call_tool("get_url_report", arguments={"url": url})
   ```

6. **get_entities_related_to_an_url** - Fetch related entities for a URL (redirects, referrers, etc.)
   ```python
   @tool
   async def get_entities_related_to_an_url(url: str, relationship: str):
       res = await session.call_tool("get_entities_related_to_an_url", arguments={
           "url": url, "relationship_name": relationship
       })
   ```

7. **get_webrisk_report** - Google Web Risk reputation check for a URL
   ```python
   @tool
   async def get_webrisk_report(url: str):
       res = await session.call_tool("get_webrisk_report", arguments={"url": url})
   ```

**Tool Binding:**
```python
llm.bind_tools([
    get_domain_report, get_entities_related_to_a_domain,
    get_ip_address_report, get_entities_related_to_an_ip_address,
    get_url_report, get_entities_related_to_an_url,
    get_webrisk_report
])
```

---

## Related Documents

- [agent_debugging_guide.md](./agent_debugging_guide.md) - Troubleshooting
- [architecture.md](./architecture.md) - System design
- [../CHANGELOG.md](../CHANGELOG.md) - Version history

---

## Lead Hunter Implementation

### File Structure

The Lead Hunter is split across three files for separation of concerns:

| File | Role |
|------|------|
| `backend/agents/lead_hunter.py` | LangGraph node entry point — mode switch (plan vs synthesize) |
| `backend/agents/lead_hunter_planning.py` | Planning phase — generates subtasks for the next specialist round |
| `backend/agents/lead_hunter_synthesis.py` | Synthesis phase — writes the final Markdown threat intelligence report |

### Workflow Integration

The Lead Hunter orchestrates the iterative investigation loop (max 3 iterations).

```mermaid
graph TD
    Triage --> Gate
    Gate -->|Parallel| Malware[Malware Specialist]
    Gate -->|Parallel| Infra[Infra Specialist]
    Malware --> LeadHunter
    Infra --> LeadHunter
    LeadHunter{Decision}
    LeadHunter -->|Continue - Planning Mode| Gate
    LeadHunter -->|End - Synthesis Mode| END
```

### Mode Switch Logic (`lead_hunter.py`)

```python
MAX_ITERATIONS = 3

if current_iteration < MAX_ITERATIONS:
    # PLANNING MODE: generate subtasks for next specialist round
    plan = await run_planning_phase(state, llm, cache)
    ...
else:
    # SYNTHESIS MODE: write final report
    final_report = await generate_final_report_llm(state, llm)
    state["subtasks"] = []  # clear to stop the loop
```

### Planning Phase (`lead_hunter_planning.py`)

Runs when `iteration < 3`. Responsibilities:
1. Gathers triage context + specialist summaries.
2. Queries NetworkX graph for all uninvestigated `file/ip/domain/url` nodes (up to 50).
3. Prompts the LLM to generate new `subtasks` JSON for the next round.
4. Returns `{"subtasks": [...]}` or `{"subtasks": []}` if no leads remain (triggers early synthesis).

### Synthesis Phase (`lead_hunter_synthesis.py`)

Runs at the final iteration (or if planning returns no tasks). Produces a comprehensive Markdown report:
- Executive Summary
- Attack Narrative (kill chain)
- Investigation Timeline
- Threat Profile, Malware Profile, Infrastructure Mapping
- Graphviz attack flow diagram
- Intelligence Gaps & Pivots
- Attribution and Context
- Hunt Hypotheses
- IOC Appendix (table format)

### Core Responsibilities
1.  **Review Work**: Analyzes specialist reports from current iteration.
2.  **Analyze Graph**: Identifies uninvestigated entities in the NetworkX cache.
3.  **Prioritize**: Selects high-value targets (malicious, central nodes).
4.  **Direct**: Generates subtasks for next iteration (planning mode).
5.  **Synthesize**: Writes holistic threat intelligence report (synthesis mode).
