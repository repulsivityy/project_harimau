# Agent Debugging & Maintenance Guide

## Overview

This document captures critical debugging patterns, common issues, and best practices for maintaining the Harimau specialist agents (Malware and Infrastructure). It represents lessons learned from production debugging sessions and should be referenced when encountering agent failures.

---

## Agent Architecture Principles

### Core Design Pattern
Both specialist agents follow an identical structural pattern:

```python
async def agent_node(state: AgentState):
    # 1. Initialize (cache, targets, MCP session)
    # 2. Define tools (@tool decorators)
    # 3. Bind tools to LLM
    # 4. Execute agentic loop (7 iterations)
    # 5. Parse LLM output (with fallback logic)
    # 6. Generate markdown report
    # 7. Update state (specialist_results, subtasks, graph)
    # 8. Return state
```

**Critical**: Maintain structural alignment between `malware.py` and `infrastructure.py`. Divergence leads to inconsistent behavior and harder maintenance.

---

## Common Issues & Solutions

### 1. JSON Parsing Errors

#### Symptom
```
ValidationError: Extra data: line X column Y
```

#### Root Cause
LLM sometimes returns JSON **arrays** `[{...}]` instead of **objects** `{...}`. The original parsing logic only handled objects.

#### Solution
Implement dual-format JSON extraction:

```python
# Detect format
array_start = clean_content.find("[")
object_start = clean_content.find("{")

if array_start != -1 and (object_start == -1 or array_start < object_start):
    # Parse as array, extract first element
    clean_content = clean_content[array_start:clean_content.rfind("]")+1]
    parsed = json.loads(clean_content)
    result = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 else {}
elif object_start != -1:
    # Parse as object  
    clean_content = clean_content[object_start:clean_content.rfind("}")+1]
    result = json.loads(clean_content)
```

**Status**: ✅ Fixed in both agents (Rev 139)

---

### 2. "LLM Returned Empty Content"

#### Symptom
Error in final parsing stage stating no content was captured from LLM.

#### Root Cause
Agent loop hits iteration limit while still making tool calls. The `final_content` variable never gets set because the loop never breaks naturally.

#### Solution
Implement robust fallback logic to search message history:

```python
# After loop finishes
if not final_content and messages:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            final_content = msg.content
            break
```

**Critical**: Fallback must check `not msg.tool_calls` to avoid capturing intermediate reasoning.

**Status**: ✅ Fixed in both agents (Rev 136)

---

### 3. MCP Tool Validation Errors

#### Symptom
```
ValidationError: Field 'ip_address' required
```
Or: "interpreting string as dictionary"

#### Root Cause
**Mismatch between three layers**:
1. **LLM call**: `get_ip_address_report(ip_address="1.2.3.4")`  
2. **Python wrapper**: `async def get_ip_address_report(ip_address: str)`
3. **MCP call**: `session.call_tool(..., arguments={"ip": ip_address})`  ❌

The MCP server expects `{"ip_address": ...}` but we were passing `{"ip": ...}`.

#### Solution
Ensure all three layers use consistent naming:

```python
@tool
async def get_ip_address_report(ip_address: str):
    """Get threat report for an IP address."""
    res = await session.call_tool(
        "get_ip_address_report", 
        arguments={"ip_address": ip_address}  # ✅ Match MCP expectation
    )
```

**Review Checklist**:
- Domain tools: `{"domain": domain}` ✅
- URL tools: `{"url": url}` ✅  
- IP tools: `{"ip_address": ip_address}` ✅

**Status**: ✅ Fixed (Rev 137)

---

### 4. Missing Specialist Reports

#### Symptom
UI shows "Unable to analyze" or empty report content.

#### Root Cause
Multiple potential causes:
1. **No targets identified**: Agent exits early before loop starts
2. **Empty LLM response**: Fallback logic missing or broken
3. **Missing error handling**: Exceptions silently swallowed

#### Solution Stack

**A. Target Discovery (Infrastructure Agent)**
```python
# Add regex fallback for missing entity_id
if not val and task.get("task"):
    # Try IP
    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", task_text)
    if ip_match: val = ip_match.group(0)
    # Try Domain, URL...
```

**B. Triage Prompt Update**
Ensure `entity_id` is explicitly requested in subtask JSON schema.

**C. Subtask Status Updates**
```python
# After successful analysis
for task in state.get("subtasks", []):
    if task.get("agent") == "infrastructure_specialist":
        task["status"] = "completed"
        task["result_summary"] = result.get("summary")
```

**Status**: ✅ Fixed (Rev 135-139)

---

## Best Practices

### Tool Definition Pattern

**❌ Avoid Pydantic Schemas** (Causes deployment crashes):
```python
# DON'T
class IpInput(BaseModel):
    ip_address: str = Field(...)

@tool(args_schema=IpInput)
async def get_ip_address_report(ip_address: str):
    ...
```

**✅ Use Simple Function Signatures**:
```python
# DO
@tool
async def get_ip_address_report(ip_address: str):
    """Get threat report for an IP address."""
    ...
```

### Error Visibility

Always include extensive error context:
```python
except Exception as e:
    state["specialist_results"]["agent"] = {
        "verdict": "System Error",
        "summary": f"Failed: {str(e)}",
        "markdown_report": f"""
## Analysis Failed

**Error**: {str(e)}

**Raw Output (2000 chars)**:
```
{str(final_text)[:2000]}
```
"""
    }
```

### Agent Loop Configuration

```python
max_iterations = 7  # Empirically determined

if iteration == max_iterations - 1:
    # Force wrap-up
    messages.append(HumanMessage(
        content="This is the final iteration. Provide comprehensive JSON."
    ))
```

---

## Deployment Checklist

Before deploying agent changes:

- [ ] **Syntax check**: `python3 -m py_compile backend/agents/{malware,infrastructure}.py`
- [ ] **Structural alignment**: Both agents follow same pattern
- [ ] **MCP arguments**: Verify `ip_address`, `domain`, `url` naming
- [ ] **JSON parsing**: Handles both arrays and objects
- [ ] **Fallback logic**: Present and not duplicated
- [ ] **Error messages**: Show 2000 chars of context
- [ ] **Subtask updates**: Status marked as "completed"

---

## Debugging Tools

### Cloud Run Logs
```bash
gcloud run services logs read harimau-backend \
  --project virustotal-lab \
  --region asia-southeast1 \
  --limit 100
```

Look for:
- `malware_agent_iteration` / `infra_agent_iteration`
- `tool_response` lengths
- `parse_error` or `fatal_error` entries

### Local Testing
```bash
# Verify imports
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -c "from backend.agents import infrastructure, malware; print('✅ OK')"
```

---

## Revision History

| Revision | Date | Changes |
|----------|------|---------|
| 139 | 2026-01-30 | JSON array/object handling, MCP argument fix, logic cleanup |
| 137 | 2026-01-30 | MCP `ip_address` argument mapping |
| 136 | 2026-01-30 | Fallback logic for empty content |
| 135 | 2026-01-30 | Pydantic removal, structural alignment |

---

## Related Documentation

- [architecture.md](./architecture.md) - System design
- [implementation_plan.md](./implementation_plan.md) - Feature roadmap
- [PRD.md](./PRD.md) - Product requirements
