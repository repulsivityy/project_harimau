# Claude AI Assistant Guide - Threat Hunter Platform

**Version:** 1.0  
**Date:** January 2025  
**Purpose:** Instructions for AI assistants helping with development  
**Audience:** Claude (and other AI coding assistants)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Document Structure](#2-document-structure)
3. [Development Workflow](#3-development-workflow)
4. [Coding Standards](#4-coding-standards)
5. [Common Tasks](#5-common-tasks)
6. [Debugging Workflow](#6-debugging-workflow)
7. [Phase-Specific Guidance](#7-phase-specific-guidance)
8. [Common Mistakes to Avoid](#8-common-mistakes-to-avoid)

---

## 1. Project Overview

### What This Project Is

The **Threat Hunter Platform** is a multi-agent AI system for automated cybersecurity investigation. It uses LangGraph to orchestrate specialized agents (Triage, Malware Hunter, Infrastructure Hunter, Synthesis) that investigate Indicators of Compromise (IOCs) and generate detailed threat intelligence reports.

**Key Characteristics:**
- **Evidence-based only:** Agents never hallucinate - all findings come from API tool responses
- **Graph-centric:** Investigation state is a NetworkX graph of IOCs and relationships
- **Budget-controlled:** Hard limits prevent runaway investigations
- **Comprehensive logging:** Two-tier logging system for normal operations and deep debugging

### Current State

**Phase:** 1 (Backend CLI)  
**Status:** In development  
**Timeline:** Weeks 1-4 (January 2025)

**What Works:**
- Project structure established
- Core data models defined
- Logging infrastructure implemented
- Basic MCP integration

**What's Next:**
- Complete agent implementations
- LangGraph workflow integration
- Benchmarking and timeout configuration

---

## 2. Document Structure

### Primary Documents

You have access to 4 main documents. Use them appropriately:

| Document | Purpose | When to Reference |
|----------|---------|-------------------|
| **PRD.md** | Product requirements, vision, timeline | Understanding "what" and "why" |
| **IMPLEMENTATION_GUIDE.md** | Complete pseudocode, technical reference | Implementing features, writing code |
| **BENCHMARKING_GUIDE.md** | Performance testing methodology | Setting timeouts, optimizing performance |
| **CLAUDE.md** (this doc) | AI assistant instructions | General guidance, workflows, patterns |

### How to Use These Docs

**When the user asks "How should I implement X?"**
→ Reference IMPLEMENTATION_GUIDE.md Section 2 (agents) or Section 3 (helpers)

**When the user asks "What are the project goals?"**
→ Reference PRD.md Section 2 (Vision & Goals)

**When the user asks "How do I run benchmarks?"**
→ Reference BENCHMARKING_GUIDE.md Section 4 (Running Benchmarks)

**When the user asks "What's the coding style?"**
→ Reference this document Section 4 (Coding Standards)

---

## 3. Development Workflow

### Week-by-Week Implementation

#### Week 1: Foundation (Current)

**Focus:** Core infrastructure before agents

**Your Role:**
1. Help set up project structure
2. Implement logging system
3. Create MCP registry
4. Write utility functions
5. Create data models

**Reference:** IMPLEMENTATION_GUIDE.md Section 2.4 (Supporting Infrastructure)

**Key Files:**
```
backend/
├── models.py              # Start here
├── logging_config.py      # Then this
├── tools/mcp_registry.py  # Then this
└── utils/                 # Finally utilities
```

---

#### Week 2: Core Agents

**Focus:** Implement 4 agents with comprehensive logging

**Your Role:**
1. Implement triage agent
2. Implement malware agent
3. Implement infrastructure agent
4. Implement synthesis agent
5. Write unit tests for each

**Reference:** IMPLEMENTATION_GUIDE.md Section 2.3 (Agents)

**Implementation Order:**
```
1. backend/agents/triage.py          # Simplest, establishes pattern
2. backend/agents/malware.py         # More complex, graph operations
3. backend/agents/infrastructure.py  # Similar to malware
4. backend/agents/synthesis.py       # Report generation
```

**For Each Agent:**
```python
# 1. Start with agent factory function
def create_agent_name(logger):
    async def agent_name(state: dict):
        # Implementation
        pass
    return agent_name

# 2. Add logging at every step
logger.log("INFO", "agent_name", "Starting analysis")

# 3. Check budget before expensive operations
can_continue, reason = state["budget"].can_continue()

# 4. Update state graph
state["graph_nodes"].append(...)

# 5. Log decisions
logger.log_decision(...)

# 6. Return updated state
return state
```

---

#### Week 3: Integration & Benchmarking

**Focus:** Wire everything together and measure performance

**Your Role:**
1. Create LangGraph workflow
2. Implement CLI interface
3. Test end-to-end
4. Create benchmark fixtures
5. Run benchmarks
6. Set timeout values

**Reference:**
- IMPLEMENTATION_GUIDE.md Section 2.2 (LangGraph)
- BENCHMARKING_GUIDE.md (complete guide)

---

### Daily Development Cycle

**1. Understand the Task**
- Read user's request carefully
- Identify which document has the answer
- Clarify ambiguities before coding

**2. Reference the Right Doc**
- For "how": IMPLEMENTATION_GUIDE.md
- For "why": PRD.md
- For "when": BENCHMARKING_GUIDE.md

**3. Write Code**
- Follow pseudocode from IMPLEMENTATION_GUIDE.md
- Add comprehensive logging
- Check budget before expensive operations
- Update graph state

**4. Explain Your Work**
- Show the code you wrote
- Explain key decisions
- Highlight any deviations from pseudocode (with reasoning)

---

## 4. Coding Standards

### Python Style

**Follow PEP 8 with these specifics:**
```python
# Imports: Standard → Third-party → Local
import os
import sys
from typing import Dict, Any

import networkx as nx
from langgraph.graph import StateGraph

from backend.models import InvestigationState
from backend.logging_config import InvestigationLogger


# Type hints always
def process_ioc(ioc: str, ioc_type: str) -> Dict[str, Any]:
    """Docstring in Google style."""
    pass


# Explicit over implicit
verdict = result.get("verdict", "UNKNOWN")  # Good
verdict = result["verdict"]  # Bad - crashes if missing


# Constants uppercase
MAX_ITERATIONS = 3
DEFAULT_TIMEOUT = 60


# Private functions prefixed with underscore
def _internal_helper():
    pass
```

---

### Logging Requirements

**Every agent must log:**

1. **Entry/Exit**
```python
logger.log("INFO", "agent_name", "Starting analysis")
# ... work ...
logger.log("INFO", "agent_name", "Analysis complete")
```

2. **Decisions**
```python
logger.log_decision(
    agent="triage",
    decision="Route to Malware Hunter",
    reasoning=f"Verdict: {verdict}, Type: file, Score: {score}"
)
```

3. **API Calls**
```python
logger.log_api_call(
    tool="gti_lookup",
    request={"ioc": ioc, "ioc_type": ioc_type},
    response=result,
    duration=duration
)
```

4. **Errors**
```python
try:
    result = await mcp_registry.call(...)
except Exception as e:
    logger.log("ERROR", "agent_name", f"API call failed: {e}")
    # Handle gracefully
```

---

### Graph Operations

**Always follow this pattern:**
```python
# 1. Check if node exists before adding
if not node_exists(state["graph_nodes"], ioc_value):
    state["graph_nodes"].append({
        "id": ioc_value,
        "type": ioc_type,
        "analyzed": False
    })
    state["budget"].nodes_created += 1

# 2. Check for cycles before adding edges
if not would_create_cycle(state["graph_edges"], source, target):
    state["graph_edges"].append({
        "source": source,
        "target": target,
        "relationship": "COMMUNICATES_WITH",
        "description": description
    })

# 3. Mark nodes as analyzed after processing
for node in state["graph_nodes"]:
    if node["id"] == ioc_value:
        node["analyzed"] = True
        break
```

---

### Error Handling

**Never let exceptions crash investigations:**
```python
# Pattern 1: Try-except with graceful degradation
try:
    result = await mcp_registry.call(...)
except Exception as e:
    logger.log("ERROR", "agent", f"Failed: {e}")
    # Continue investigation with partial results
    return state

# Pattern 2: Validate data before using
if not result or "data" not in result:
    logger.log("WARN", "agent", "Invalid API response")
    return state

# Pattern 3: Use .get() with defaults
score = result.get("score", 0)
verdict = result.get("verdict", "UNKNOWN")
```

---

## 5. Common Tasks

### Task: Implement a New Agent

**Steps:**

1. **Create file:** `backend/agents/agent_name.py`

2. **Copy template from IMPLEMENTATION_GUIDE.md** (Section 2.3)

3. **Customize for your agent:**
```python
def create_agent_name(logger):
    async def agent_name(state: dict):
        logger.log("INFO", "agent_name", "Starting")
        
        # 1. Find work to do
        items = find_unanalyzed_items(state["graph_nodes"])
        
        # 2. Process each item
        for item in items:
            # Check budget
            can_continue, reason = state["budget"].can_continue()
            if not can_continue:
                logger.log("WARN", "agent_name", f"Budget exhausted: {reason}")
                break
            
            # Make API call
            result = await mcp_registry.call(...)
            
            # Log API call
            logger.log_api_call(...)
            
            # Update graph
            state["graph_nodes"].append(...)
            state["graph_edges"].append(...)
            
            # Update budget
            state["budget"].api_calls_made += 1
        
        # 3. Track execution
        state["agents_run"].append("agent_name")
        logger.log("INFO", "agent_name", "Complete")
        
        return state
    
    return agent_name
```

4. **Write tests:** `tests/test_agent_name.py`

5. **Add to workflow:** Update `backend/graph_workflow.py`

---

### Task: Add Logging to Existing Code

**Before:**
```python
result = await mcp_registry.call("gti", "lookup_ioc", {"ioc": ioc})
verdict = result["verdict"]
```

**After:**
```python
logger.log("INFO", "agent", f"Querying GTI for {ioc}")

try:
    result = await mcp_registry.call("gti", "lookup_ioc", {"ioc": ioc})
    
    logger.log_api_call(
        tool="gti_lookup",
        request={"ioc": ioc},
        response=result,
        duration=result.get("_duration", 0)
    )
    
    verdict = result.get("verdict", "UNKNOWN")
    logger.log("INFO", "agent", f"GTI verdict: {verdict}")
    
except Exception as e:
    logger.log("ERROR", "agent", f"GTI lookup failed: {e}")
    verdict = "ERROR"
```

---

### Task: Debug a Failing Investigation

**Workflow:**

1. **Get investigation ID** from CLI output

2. **Check normal logs:**
```bash
cat logs/normal/investigation_inv-123.log
```

3. **Look for errors or unusual patterns:**
```bash
grep "ERROR" logs/normal/investigation_inv-123.log
grep "DECISION" logs/normal/investigation_inv-123.log
```

4. **If debug mode was enabled, check detailed logs:**
```bash
# API calls
ls logs/debug/inv-123_api_calls/

# LLM prompts
ls logs/debug/inv-123_llm_prompts/

# State snapshots
cat logs/debug/inv-123_state_snapshots/after_triage.json
```

5. **Identify root cause** and propose fix

---

### Task: Add a New Tool to MCP Registry

**Steps:**

1. **Update `backend/tools/mcp_registry.py`:**
```python
self.servers = {
    "gti": { ... },
    "shodan": { ... },
    "new_tool": {  # Add this
        "url": os.getenv("NEW_TOOL_MCP_URL", "http://localhost:3003"),
        "capabilities": ["capability1", "capability2"]
    }
}
```

2. **Test connection:**
```python
# In Python console or test file
from backend.tools.mcp_registry import mcp_registry

result = await mcp_registry.call(
    server="new_tool",
    tool="capability1",
    args={"param": "value"}
)
print(result)
```

3. **Update agents** to use new tool

4. **Document** in README.md

---

## 6. Debugging Workflow

### Scenario: Agent Made Wrong Decision

**Example:** Triage routed a malicious file to Infrastructure instead of Malware

**Debug Steps:**

1. **Find the decision log entry:**
```bash
grep "DECISION.*triage" logs/normal/investigation_inv-123.log
```

Output:
```
[2025-01-20 14:32:15] [inv-123] [triage] DECISION: Route to Infrastructure Hunter
```

2. **Check the reasoning:**
```bash
grep -A 5 "DECISION.*triage" logs/normal/investigation_inv-123.log
```

3. **If debug mode enabled, check LLM prompt:**
```bash
cat logs/debug/inv-123_llm_prompts/001_triage_prompt.txt
```

4. **Check API response that informed decision:**
```bash
cat logs/debug/inv-123_api_calls/001_gti_lookup_response.json
```

5. **Identify issue:**
- Prompt unclear?
- API response missing key field?
- Logic error in routing?

6. **Fix and re-test**

---

### Scenario: Investigation Timeout

**Example:** Investigation ran for 15 minutes and was killed

**Debug Steps:**

1. **Check budget status:**
```bash
grep "Budget" logs/normal/investigation_inv-123.log
```

2. **Look for wall time exhaustion:**
```
[2025-01-20 14:47:15] [inv-123] [system] WARN: Budget exhausted: Investigation timeout (602s/600s)
```

3. **Check how far it got:**
```bash
tail -20 logs/normal/investigation_inv-123.log
```

4. **Look at final state:**
```bash
cat logs/debug/inv-123_state_snapshots/final.json | jq '.iteration, .graph_nodes | length'
```

5. **Determine cause:**
- Stuck in iteration loop?
- Processing too many nodes?
- API calls timing out?

6. **Possible fixes:**
- Increase wall time limit
- Add per-iteration limits
- Optimize slow agent

---

### Scenario: Graph Has Cycles

**Example:** Investigation created circular reference A → B → A

**Debug Steps:**

1. **Check graph edges:**
```bash
cat logs/debug/inv-123_state_snapshots/final.json | jq '.graph_edges'
```

2. **Identify the cycle:**
```json
[
  {"source": "A", "target": "B", "relationship": "DROPPED"},
  {"source": "B", "target": "A", "relationship": "COMMUNICATES_WITH"}
]
```

3. **Find which agent added the problematic edge:**
```bash
grep "Graph Edge.*source.*A.*target.*B" logs/normal/investigation_inv-123.log
```

4. **Fix:** Ensure `would_create_cycle()` is called before adding edges

---

## 7. Phase-Specific Guidance

### Phase 1: Backend CLI (Current)

**Your Focus:**
- Implement core functionality
- Add comprehensive logging
- Test with manual CLI invocations
- Establish performance baselines

**NOT Your Focus:**
- HTTP APIs (Phase 2)
- Web frontend (Phase 3)
- Authentication (Phase 2)
- Database persistence (deferred)

**When User Asks About Future Features:**
- Acknowledge the feature is planned
- Reference PRD.md for timeline
- Suggest focus on Phase 1 completion first

---

### Phase 2: HTTP APIs (Future)

**Will Add:**
- FastAPI server
- REST endpoints
- Async job queue
- Basic authentication

**Preparation Now:**
- Keep business logic in agents (not CLI)
- Make functions reusable
- Avoid CLI-specific dependencies in core code

---

### Phase 3: Web Frontend (Future)

**Will Add:**
- React frontend
- Interactive graph visualization
- Real-time progress updates

**Preparation Now:**
- Structure reports for programmatic parsing
- Keep graph in JSON-serializable format
- Log progress events (can be streamed later)

---

## 8. Common Mistakes to Avoid

### ❌ Mistake 1: Hardcoding Instead of Using Config

**Bad:**
```python
MAX_ITERATIONS = 3  # Hardcoded in agent
```

**Good:**
```python
max_iterations = state["max_iterations"]  # From config
```

**Why:** User should control limits, not code

---

### ❌ Mistake 2: Not Checking Budget

**Bad:**
```python
for ioc in unanalyzed_iocs:
    result = await mcp_registry.call(...)  # No budget check!
```

**Good:**
```python
for ioc in unanalyzed_iocs:
    can_continue, reason = state["budget"].can_continue()
    if not can_continue:
        logger.log("WARN", "agent", f"Budget exhausted: {reason}")
        break
    
    result = await mcp_registry.call(...)
```

**Why:** Prevents runaway investigations

---

### ❌ Mistake 3: Assuming API Responses Are Complete

**Bad:**
```python
score = result["score"]  # Crashes if missing!
```

**Good:**
```python
score = result.get("score", 0)
```

**Why:** APIs can return incomplete data

---

### ❌ Mistake 4: Not Logging Decisions

**Bad:**
```python
if verdict == "MALICIOUS":
    return "malware"
else:
    return "infrastructure"
```

**Good:**
```python
if verdict == "MALICIOUS":
    logger.log_decision(
        agent="router",
        decision="Route to Malware Hunter",
        reasoning=f"Verdict: {verdict}, Type: file"
    )
    return "malware"
else:
    logger.log_decision(
        agent="router",
        decision="Route to Infrastructure Hunter",
        reasoning=f"Verdict: {verdict}, Type: network"
    )
    return "infrastructure"
```

**Why:** Decisions need to be traceable for debugging

---

### ❌ Mistake 5: Creating Duplicate Nodes

**Bad:**
```python
state["graph_nodes"].append({
    "id": ioc,
    "type": ioc_type
})  # Might already exist!
```

**Good:**
```python
if not node_exists(state["graph_nodes"], ioc):
    state["graph_nodes"].append({
        "id": ioc,
        "type": ioc_type
    })
    state["budget"].nodes_created += 1
```

**Why:** Duplicate nodes break graph logic

---

### ❌ Mistake 6: Not Marking Nodes as Analyzed

**Bad:**
```python
for file_hash in files_to_analyze:
    result = await get_behavior(file_hash)
    # Forgot to mark as analyzed!
```

**Good:**
```python
for file_hash in files_to_analyze:
    result = await get_behavior(file_hash)
    
    # Mark as analyzed
    for node in state["graph_nodes"]:
        if node["id"] == file_hash:
            node["analyzed"] = True
            break
```

**Why:** Unanalyzed nodes will be re-processed in next iteration

---

### ❌ Mistake 7: Using Sync Code in Async Functions

**Bad:**
```python
async def agent(state):
    result = requests.get(url)  # Blocking!
```

**Good:**
```python
async def agent(state):
    result = await mcp_registry.call(...)  # Non-blocking
```

**Why:** Blocking calls defeat async performance benefits

---

### ❌ Mistake 8: Not Handling Cycles

**Bad:**
```python
state["graph_edges"].append({
    "source": source,
    "target": target
})  # Might create cycle!
```

**Good:**
```python
if not would_create_cycle(state["graph_edges"], source, target):
    state["graph_edges"].append({
        "source": source,
        "target": target
    })
else:
    logger.log("WARN", "agent", f"Skipping edge {source}→{target} (would create cycle)")
```

**Why:** Cycles break graph algorithms and visualization

---

## 9. Quick Reference

### Essential Files Reference

| File | Purpose | Key Functions |
|------|---------|---------------|
| `backend/models.py` | Data models | `InvestigationState`, `InvestigationBudget` |
| `backend/logging_config.py` | Logging | `InvestigationLogger.log()`, `log_decision()` |
| `backend/tools/mcp_registry.py` | MCP calls | `mcp_registry.call()` |
| `backend/graph_workflow.py` | LangGraph | `create_investigation_workflow()` |
| `backend/cli.py` | CLI entry | `run_investigation()` |

---

### Common Code Snippets

**Check budget:**
```python
can_continue, reason = state["budget"].can_continue()
if not can_continue:
    logger.log("WARN", agent, f"Budget exhausted: {reason}")
    return state
```

**Add node safely:**
```python
if not node_exists(state["graph_nodes"], ioc):
    state["graph_nodes"].append({"id": ioc, "type": ioc_type, "analyzed": False})
    state["budget"].nodes_created += 1
```

**Log API call:**
```python
logger.log_api_call(
    tool="gti_lookup",
    request={"ioc": ioc},
    response=result,
    duration=result.get("_duration", 0)
)
```

**Mark node analyzed:**
```python
for node in state["graph_nodes"]:
    if node["id"] == target_ioc:
        node["analyzed"] = True
        break
```

---

### Testing Commands
```bash
# Run single investigation
python backend/cli.py investigate <IOC>

# Run with debug mode
python backend/cli.py investigate <IOC> --debug

# Run unit tests
pytest tests/

# Run specific test
pytest tests/test_triage.py::test_classify_file_hash

# Run benchmarks
python tests/benchmark.py

# Check logs
tail -f logs/normal/investigation_*.log
```

---

## 10. How to Help the User

### When They're Stuck

**Good Response:**
```
I see you're working on the Malware Hunter agent. Let me reference the 
IMPLEMENTATION_GUIDE.md Section 2.3.2 which has the complete pseudocode.

The key steps are:
1. Find unanalyzed file hashes
2. Check budget before each API call
3. Extract network IOCs from behavior
4. Add nodes/edges to graph
5. Mark files as analyzed

Here's the code for step 1:
[provide code]

Would you like me to continue with the other steps?
```

**Bad Response:**
```
Just implement it however you think is best.
```

---

### When They Ask "How Should I...?"

**Pattern:**
1. Identify which document has the answer
2. Reference specific section
3. Provide code example
4. Explain the reasoning

**Example:**
```
User: "How should I log API calls?"

Response: "According to IMPLEMENTATION_GUIDE.md Section 2.4.3, you should 
use the InvestigationLogger.log_api_call() method. Here's the pattern:

[code example]

This creates a normal log entry plus saves full request/response payloads 
in debug mode for troubleshooting."
```

---

### When They Want to Deviate

**If deviation makes sense:**
```
That's a good idea. The pseudocode suggests X, but your approach Y would 
actually be better because [reasoning]. Let's implement Y and document why 
we deviated in a code comment.
```

**If deviation is problematic:**
```
I understand the appeal of approach Y, but the IMPLEMENTATION_GUIDE.md 
specifies X because [reasoning]. If we use Y instead, we might break 
[specific functionality]. Can we achieve your goal while sticking with X?
```

---

### When Documentation is Unclear

**Don't guess - ask for clarification:**
```
The IMPLEMENTATION_GUIDE.md says to "extract network IOCs" but doesn't 
specify the exact format. Looking at the data models in backend/models.py, 
I see the expected structure is:

[show structure]

Should I use this format, or would you like to clarify?
```

---

## 11. Final Reminders

### Core Principles

1. **Evidence-based only** - Never hallucinate findings
2. **Comprehensive logging** - Every decision must be traceable
3. **Budget-controlled** - Always check limits
4. **Graceful degradation** - Handle errors, don't crash

### When in Doubt

1. **Check the docs** - Answer is probably in IMPLEMENTATION_GUIDE.md
2. **Look at existing code** - Follow established patterns
3. **Ask the user** - Better to clarify than implement wrong

### Success Metrics

You're doing well if:
- ✅ Code follows pseudocode from IMPLEMENTATION_GUIDE.md
- ✅ Every decision is logged
- ✅ Budget is checked before expensive operations
- ✅ Errors are handled gracefully
- ✅ Tests are written
- ✅ User understands your code

---

## Appendix: Document Cross-Reference Map

**User asks about...**

| Topic | Primary Doc | Supporting Doc |
|-------|------------|----------------|
| Project goals | PRD.md § 2 | - |
| Architecture | PRD.md § 4 | IMPLEMENTATION_GUIDE.md § 2 |
| Timeline | PRD.md § 5 | - |
| Agent implementation | IMPLEMENTATION_GUIDE.md § 2.3 | PRD.md § 4.2 |
| LangGraph workflow | IMPLEMENTATION_GUIDE.md § 2.2 | - |
| Logging | IMPLEMENTATION_GUIDE.md § 2.4.3 | This doc § 4 |
| MCP integration | IMPLEMENTATION_GUIDE.md § 2.4.2 | PRD.md § 4.5 |
| Testing | IMPLEMENTATION_GUIDE.md § 5 | - |
| Benchmarking | BENCHMARKING_GUIDE.md | - |
| Timeout values | BENCHMARKING_GUIDE.md § 6 | - |
| Coding style | This doc § 4 | - |
| Common mistakes | This doc § 8 | - |
| Debugging | This doc § 6 | IMPLEMENTATION_GUIDE.md § 6 |

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Maintained By:** Development Team  
**Related Docs:** [PRD.md](./PRD.md), [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md), [BENCHMARKING_GUIDE.md](./BENCHMARKING_GUIDE.md)