# Phase 5.2: Lead Threat Hunter - Technical Specification

## Overview

The Lead Threat Hunter is the orchestration agent that enables iterative malware investigation by:
1. Reviewing specialist findings after each iteration
2. Analyzing the expanded investigation graph 
3. Identifying and prioritizing uninvestigated entities
4. Directing specialists to investigate high-value targets
5. Generating holistic synthesis reports
6. Managing iteration limits (max 3 iterations)

---

## Architecture

### Workflow Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    ITERATION LOOP (Max 3)                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Iteration 0:                                               │
│  ┌────────┐              ┌──────────────────────┐          │
│  │ Triage │─────────────▶│ Specialist Gate      │          │
│  └────────┘              └──────────────────────┘          │
│                                   │                         │
│                          ┌────────┴─────────┐              │
│                          ▼                  ▼               │
│                    ┌──────────┐      ┌────────────┐        │
│                    │ Malware  │      │    Infra   │        │
│                    │Specialist│      │ Specialist │        │
│                    └──────────┘      └────────────┘        │
│                          │                  │               │
│                          └────────┬─────────┘              │
│                                   ▼                         │
│                          ┌─────────────────┐               │
│                          │ Lead Threat     │               │
│                          │ Hunter          │               │
│                          │                 │               │
│                          │ - Review work   │               │
│                          │ - Find new IOCs │               │
│                          │ - Prioritize    │               │
│                          │ - Create tasks  │               │
│                          └─────────────────┘               │
│                                   │                         │
│                          ┌────────┴────────┐               │
│                          ▼                 ▼                │
│                    ┌──────────┐      ┌─────────┐          │
│                    │Continue? │      │   END   │          │
│                    │(Loop back│      │         │          │
│                    │ to Gate) │      │         │          │
│                    └──────────┘      └─────────┘          │
│                          │                                  │
│                          └──────────┐                      │
│                                     │                       │
│  ───────────────────────────────────┘                      │
│  Iteration 1: (Same Flow)                                  │
│  Iteration 2: (Same Flow)                                  │
│  Iteration 3: Force END                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Decision Logic

```python
def should_continue_investigation(state: AgentState) -> str:
    """
    Lead Hunter decides: Continue or End
    
    Returns:
        "continue": Loop back to gate for next iteration
        END: Stop investigation
    """
    iteration = state.get("iteration", 0)
    max_iterations = 3
    subtasks = state.get("subtasks", [])
    
    # Hard stop at max iterations
    if iteration >= max_iterations:
        return END
    
    # No new work identified
    if not subtasks:
        return END
    
    # Continue to next iteration
    return "continue"
```

---

## Component Implementation

### 1. Lead Hunter Agent

**File:** `backend/agents/lead_hunter.py`

#### Core Function

```python
async def lead_hunter_node(state: AgentState) -> AgentState:
    """
    Lead Threat Hunter: Orchestrates iterative investigation.
    
    Workflow:
    1. Retrieve iteration context
    2. Load investigation graph
    3. Gather all previous findings
    4. Identify uninvestigated entities
    5. LLM analysis: What should we investigate next?
    6. Create subtasks for next iteration
    7. Generate synthesis report
    8. Update iteration count
    
    Returns:
        Updated state with:
        - subtasks: List of new tasks for specialists
        - iteration: Incremented counter
        - lead_hunter_report: Synthesis markdown
        - metadata.rich_intel.lead_hunter_analysis: Structured data
    """
    logger.info("lead_hunter_start", iteration=state.get("iteration", 0))
    
    try:
        # === 1. CONTEXT GATHERING ===
        iteration = state.get("iteration", 0)
        max_iterations = 3
        ioc = state["ioc"]
        
        # Initialize cache
        cache = InvestigationCache(state.get("investigation_graph"))
        cache_stats = cache.get_stats()
        
        # Get previous reports
        triage_analysis = state.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
        specialist_results = state.get("specialist_results", {})
        malware_report = specialist_results.get("malware", {})
        infra_report = specialist_results.get("infrastructure", {})
        
        # === 2. GRAPH ANALYSIS ===
        uninvestigated = cache.get_uninvestigated_nodes()
        logger.info("lead_hunter_graph_analysis", 
                   total_nodes=cache_stats.get("nodes", 0),
                   uninvestigated_count=len(uninvestigated))
        
        # === 3. LLM DECISION MAKING ===
        project_id  = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
        llm = ChatVertexAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            project=project_id,
            location=location
        )
        
        # Build comprehensive context
        context_prompt = build_lead_hunter_context(
            iteration=iteration,
            max_iterations=max_iterations,
            triage=triage_analysis,
            malware=malware_report,
            infra=infra_report,
            graph_stats=cache_stats,
            uninvestigated=uninvestigated
        )
        
        messages = [
            SystemMessage(content=LEAD_HUNTER_PROMPT),
            HumanMessage(content=context_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        
        # === 4. PARSE LLM RESPONSE ===
        analysis = parse_lead_hunter_response(response.content)
        
        # === 5. UPDATE STATE ===
        # Create subtasks for next iteration
        new_subtasks = analysis.get("subtasks", [])
        state["subtasks"] = new_subtasks
        
        # Increment iteration
        if new_subtasks:
            state["iteration"] = iteration + 1
        
        # Store synthesis report
        synthesis_report = generate_lead_hunter_markdown(analysis, iteration)
        state["lead_hunter_report"] = synthesis_report
        
        # Store structured data
        if "metadata" not in state:
            state["metadata"] = {}
        if "rich_intel" not in state["metadata"]:
            state["metadata"]["rich_intel"] = {}
        state["metadata"]["rich_intel"]["lead_hunter_analysis"] = analysis
        
        logger.info("lead_hunter_complete", 
                   iteration=iteration,
                   next_iteration=state.get("iteration"),
                   new_subtasks=len(new_subtasks),
                   decision=analysis.get("decision"))
        
        return state
        
    except Exception as e:
        logger.error("lead_hunter_error", error=str(e))
        # Don't fail the whole investigation - just end gracefully
        state["subtasks"] = []
        return state
```

#### LLM Prompt

```python
LEAD_HUNTER_PROMPT = """You are the **Lead Threat Intelligence Hunter** orchestrating a malware investigation.

## Role

You are the senior analyst who reviews specialist work and strategically directs the investigation. You think in terms of:
- **Attack Chains**: Initial compromise → Lateral movement → C2 → Data exfiltration
- **Threat Actor TTPs**: What techniques, tools, and procedures are being used?
- **Investigative Value**: Which entities will give us the most insight?
- **Resource Management**: Limited to 3 iteration cycles

## Your Responsibilities

### 1. Review Previous Work
- **Triage Report**: Initial assessment of the root IOC
- **Malware Specialist**: File analysis (behavior, capabilities, dropped files, C2)
- **Infrastructure Specialist**: Network analysis (IPs, domains, URLs, campaigns)

### 2. Analyze Investigation Graph
- **Current State**: How many entities discovered? What types?
- **Coverage**: What percentage has been analyzed?
- **Gaps**: What high-value entities remain uninvestigated?

### 3. Prioritize Next Actions
Apply these criteria:
- **Malicious Verdict**: Entities flagged as malicious (highest priority)
- **Attack Chain Centrality**: C2 servers, droppers, final payloads
- **Novelty**: New threat families, previously unseen infrastructure
- **Relationship Density**: Entities with many connections (hubs)

### 4. Direct Specialists
Create specific, actionable subtasks:
```json
{
    "agent": "malware_specialist|infrastructure_specialist",
    "task": "Analyze dropped file found in %TEMP% directory",
    "entity_id": "SHA256_HASH or IP or DOMAIN",
    "context": "Triage identified this as a secondary payload. Previous analysis shows it contacts C2 at 192.0.2.1"
}
```

### 5. Synthesize Findings
Write a holistic report that:
- Tells the **attack narrative** from start to end
- Highlights **key findings** and **IOCs**
- Provides **defensive recommendations**
- Notes **investigation gaps** (if any)

## Decision Criteria

### CONTINUE Investigation If:
- High-priority malicious entities remain uninvestigated
- Attack chain is incomplete (missing C2, payload, etc.)
- New threat actor/campaign discovered
- Iteration < 3

### END Investigation If:
- Iteration >= 3 (hard limit)
- No uninvestigated entities of value
- Attack chain fully mapped
- Diminishing returns (new entities are benign/low-value)

## Output Format (JSON)

```json
{
    "summary": "Concise 2-3 sentence overview of investigation status",
    "attack_narrative": "Complete story: How did the attack unfold? Initial vector → Execution → Persistence → C2 → Impact",
    "key_findings": [
        "Finding 1: Malware family identified as Emotet variant",
        "Finding 2: C2 infrastructure hosted on bulletproof hosting (AS12345)",
        "Finding 3: Secondary payload is Cobalt Strike beacon"
    ],
    "iocs": {
        "files": ["hash1", "hash2"],
        "ips": ["1.2.3.4", "5.6.7.8"],
        "domains": ["evil.com", "bad.net"],
        "urls": ["http://evil.com/payload.exe"]
    },
    "priority_targets": [
        {
            "entity_id": "abc123def456...",
            "entity_type": "file",
            "verdict": "malicious",
            "priority": "high",
            "rationale": "Dropped by initial malware, suspected to be final payload"
        },
        {
            "entity_id": "192.0.2.1",
            "entity_type": "ip_address",
            "verdict": "malicious",
            "priority": "high",
            "rationale": "C2 server contacted by multiple samples, central to infrastructure"
        }
    ],
    "subtasks": [
        {
            "agent": "malware_specialist",
            "task": "Analyze suspected final payload",
            "entity_id": "abc123def456...",
            "context": "Dropped by initial dropper. Likely Cobalt Strike based on triage findings."
        }
    ],
    "decision": "continue|end",
    "decision_rationale": "Explanation of why we should continue/end",
    "defensive_recommendations": [
        "Block C2 IPs at firewall",
        "Hunt for file hash across environment",
        "Monitor for similar TTPs"
    ]
}
```

## Important Rules

1. **Iteration Limit**: If `iteration >= 3`, you MUST set `"decision": "end"` and `"subtasks": []`
2. **Subtask Limit**: Maximum 5 subtasks per iteration (focus on highest value)
3. **Entity Types**: Only investigate entities you can route:
   - Files/Hashes → `malware_specialist`
   - IPs/Domains/URLs → `infrastructure_specialist`
4. **Context is King**: Always provide context to specialists explaining WHY they're investigating this entity
5. **No Speculation**: Base recommendations on actual findings, not assumptions
"""
```

#### Helper Functions

```python
def build_lead_hunter_context(
    iteration: int,
    max_iterations: int,
    triage: dict,
    malware: dict,
    infra: dict,
    graph_stats: dict,
    uninvestigated: List[dict]
) -> str:
    """
    Build comprehensive context for Lead Hunter LLM.
    """
    context = f"""# Investigation Context

## Iteration Status
- Current Iteration: {iteration}
- Max Iterations: {max_iterations}
- Iterations Remaining: {max_iterations - iteration}

## Triage Report Summary
**Root IOC**: {triage.get('ioc', 'N/A')}
**Verdict**: {triage.get('verdict', 'N/A')}
**Executive Summary**:
{triage.get('executive_summary', 'No summary available')}

**Key Findings**:
"""
    
    for finding in triage.get('key_findings', []):
        context += f"- {finding}\n"
    
    context += f"\n\n## Specialist Reports\n\n"
    
    # Malware Report
    if malware:
        context += f"""### Malware Specialist Analysis
**Verdict**: {malware.get('verdict', 'N/A')}
**Family**: {malware.get('family', 'N/A')}
**Intent**: {malware.get('intent', 'N/A')}
**Summary**: {malware.get('summary', 'N/A')}

**Network Indicators Found**: {', '.join(malware.get('network_indicators', [])[:5])}
**Host Indicators Found**: {', '.join(malware.get('host_indicators', [])[:5])}

"""
    
    # Infrastructure Report
    if infra:
        context += f"""### Infrastructure Specialist Analysis
**Verdict**: {infra.get('verdict', 'N/A')}
**Threat Score**: {infra.get('threat_score', 'N/A')}
**Categories**: {', '.join(infra.get('categories', []))}
**Summary**: {infra.get('summary', 'N/A')}

**Related Indicators Found**: {', '.join(infra.get('related_indicators', [])[:5])}

"""
    
    # Graph Statistics
    context += f"""## Investigation Graph Statistics
- Total Nodes: {graph_stats.get('nodes', 0)}
- Total Edges: {graph_stats.get('edges', 0)}
- Nodes by Type: {graph_stats.get('nodes_by_type', {})}
- Analyzed Nodes: {graph_stats.get('analyzed_count', 0)}
- **Uninvestigated Nodes: {len(uninvestigated)}**

## Uninvestigated Entities

"""
    
    # Group uninvestigated by type and verdict
    malicious_uninvestigated = [e for e in uninvestigated if e.get('attributes', {}).get('verdict') == 'malicious']
    suspicious_uninvestigated = [e for e in uninvestigated if e.get('attributes', {}).get('verdict') == 'suspicious']
    unknown_uninvestigated = [e for e in uninvestigated if e.get('attributes', {}).get('verdict') not in ['malicious', 'suspicious']]
    
    context += f"### Malicious Entities ({len(malicious_uninvestigated)}):\n"
    for entity in malicious_uninvestigated[:10]:  # Limit to top 10
        context += f"- **{entity['type']}**: {entity['id'][:50]}... (Verdict: {entity.get('attributes', {}).get('verdict')})\n"
    
    context += f"\n### Suspicious Entities ({len(suspicious_uninvestigated)}):\n"
    for entity in suspicious_uninvestigated[:5]:  # Limit to top 5
        context += f"- **{entity['type']}**: {entity['id'][:50]}... (Verdict: {entity.get('attributes', {}).get('verdict')})\n"
    
    context += f"\n### Unknown/Benign Entities ({len(unknown_uninvestigated)}):\n"
    context += f"_(Showing first 3 of {len(unknown_uninvestigated)})_\n"
    for entity in unknown_uninvestigated[:3]:
        context += f"- **{entity['type']}**: {entity['id'][:50]}...\n"
    
    context += "\n\n## Your Task\n\n"
    context += "Based on the above context, decide:\n"
    context += "1. Should we continue investigating? (If iteration < 3 and high-value targets exist)\n"
    context += "2. Which entities should specialists analyze next? (Prioritize malicious, attack-chain-relevant)\n"
    context += "3. What is the holistic attack narrative so far?\n"
    context += "4. What defensive actions should be taken?\n"
    
    return context


def parse_lead_hunter_response(content: str) -> dict:
    """
    Parse LLM response into structured dict.
    Handles markdown code blocks and extracts JSON.
    """
    # Handle list responses (Gemini sometimes returns list of content blocks)
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
            else:
                text_parts.append(str(block))
        content = "".join(text_parts).strip()
    else:
        content = str(content or "").strip()
    
    # Clean markdown
    if "```json" in content:
        content = content.split("```json")[-1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].strip() if content.count("```") >= 2 else content
    
    # Extract JSON
    import re
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if json_match:
        content = json_match.group(0)
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("lead_hunter_json_parse_error", error=str(e), content=content[:200])
        raise ValueError(f"Could not parse Lead Hunter response as JSON: {str(e)}")


def generate_lead_hunter_markdown(analysis: dict, iteration: int) -> str:
    """
    Generate markdown report from Lead Hunter analysis.
    """
    md = f"## Lead Threat Hunter - Iteration {iteration} Report\n\n"
    
    md += "### Investigation Summary\n"
    md += f"{analysis.get('summary', 'No summary provided')}\n\n"
    
    md += "### Attack Narrative\n"
    md += f"{analysis.get('attack_narrative', 'No narrative provided')}\n\n"
    
    # Key Findings
    findings = analysis.get('key_findings', [])
    if findings:
        md += "### Key Findings\n"
        for finding in findings:
            md += f"- {finding}\n"
        md += "\n"
    
    # IOCs
    iocs = analysis.get('iocs', {})
    if iocs:
        md += "### Indicators of Compromise (IOCs)\n"
        if iocs.get('files'):
            md += f"**Files**: `{', '.join(iocs['files'][:5])}`\n\n"
        if iocs.get('ips'):
            md += f"**IP Addresses**: `{', '.join(iocs['ips'][:5])}`\n\n"
        if iocs.get('domains'):
            md += f"**Domains**: `{', '.join(iocs['domains'][:5])}`\n\n"
        if iocs.get('urls'):
            md += f"**URLs**: `{', '.join(iocs['urls'][:3])}`\n\n"
    
    # Priority Targets
    targets = analysis.get('priority_targets', [])
    if targets:
        md += "### Priority Investigation Targets\n"
        for target in targets:
            md += f"- **{target.get('entity_type')}** `{target.get('entity_id')[:50]}...`\n"
            md += f"  - Priority: {target.get('priority')}\n"
            md += f"  - Rationale: {target.get('rationale')}\n\n"
    
    # Decision
    md += f"### Decision: {analysis.get('decision', 'unknown').upper()}\n"
    md += f"{analysis.get('decision_rationale', 'No rationale provided')}\n\n"
    
    # Defensive Recommendations
    recommendations = analysis.get('defensive_recommendations', [])
    if recommendations:
        md += "### Defensive Recommendations\n"
        for rec in recommendations:
            md += f"- {rec}\n"
    
    return md
```

---

### 2. Graph Cache Enhancement

**File:** `backend/utils/graph_cache.py`

**New Method:**

```python
def get_uninvestigated_nodes(self) -> List[dict]:
    """
    Returns entities that haven't been analyzed by any specialist.
    
    A node is considered "investigated" if it has the `analyzed_by` attribute
    set by a specialist agent.
    
    Returns:
        List of dicts with structure:
        [
            {
                "id": "entity_id",
                "type": "file|ip_address|domain|url",
                "attributes": {...}
            },
            ...
        ]
    """
    uninvestigated = []
    
    for node_id, node_data in self.graph.nodes(data=True):
        analyzed_by = node_data.get("analyzed_by", [])
        
        # If no specialist has analyzed this node
        if not analyzed_by:
            uninvestigated.append({
                "id": node_id,
                "type": node_data.get("type", "unknown"),
                "attributes": node_data
            })
    
    return uninvestigated
```

---

### 3. Workflow Modifications

**File:** `backend/graph/workflow.py`

**Changes:**

```python
from backend.agents.lead_hunter import lead_hunter_node

def build_graph():
    """
    Phase 5.2: Triage → Gate → Specialists → Lead Hunter → (Loop or END)
    """
    workflow = StateGraph(AgentState)
    
    # === NODES ===
    workflow.add_node("triage", triage_node)
    workflow.add_node("gate", gate_node)  # NEW
    workflow.add_node("malware_specialist", malware_node)
    workflow.add_node("infrastructure_specialist", infrastructure_node)
    workflow.add_node("lead_hunter", lead_hunter_node)  # NEW
    
    # === EDGES ===
    workflow.set_entry_point("triage")
    
    # Triage → Gate (first time)
    workflow.add_edge("triage", "gate")
    
    # Gate → Specialists (conditional, parallel)
    workflow.add_conditional_edges(
        "gate",
        route_from_gate,
        {
            "malware_specialist": "malware_specialist",
            "infrastructure_specialist": "infrastructure_specialist",
            "lead_hunter": "lead_hunter"  # If no subtasks, go directly to lead hunter
        }
    )
    
    # Specialists → Lead Hunter (fan-in)
    workflow.add_edge("malware_specialist", "lead_hunter")
    workflow.add_edge("infrastructure_specialist", "lead_hunter")
    
    # Lead Hunter → Decision (continue or end)
    workflow.add_conditional_edges(
        "lead_hunter",
        route_from_lead_hunter,
        {
            "gate": "gate",  # Loop back for next iteration
            END: END
        }
    )
    
    return workflow.compile()


def gate_node(state: AgentState) -> AgentState:
    """
    No-op routing node. Actual routing logic is in conditional edge.
    Logs current iteration for debugging.
    """
    iteration = state.get("iteration", 0)
    subtasks = state.get("subtasks", [])
    logger.info("gate_node", iteration=iteration, subtask_count=len(subtasks))
    return state


def route_from_gate(state: AgentState):
    """
    Route to appropriate specialists based on subtasks.
    Returns list of specialist nodes to invoke in parallel.
    """
    subtasks = state.get("subtasks", [])
    next_nodes = []
    
    for task in subtasks:
        agent = task.get("agent")
        if agent in ["malware_specialist", "malware"] and "malware_specialist" not in next_nodes:
            next_nodes.append("malware_specialist")
        elif agent in ["infrastructure_specialist", "infrastructure"] and "infrastructure_specialist" not in next_nodes:
            next_nodes.append("infrastructure_specialist")
    
    # If no subtasks, skip specialists and go directly to lead hunter
    if not next_nodes:
        return ["lead_hunter"]
    
    return next_nodes


def route_from_lead_hunter(state: AgentState):
    """
    Decide if we should continue investigating or end.
    
    Returns:
        "gate": Loop back for next iteration
        END: Stop investigation
    """
    iteration = state.get("iteration", 0)
    max_iterations = 3
    subtasks = state.get("subtasks", [])
    
    logger.info("lead_hunter_routing",
               iteration=iteration,
               max_iterations=max_iterations,
               has_subtasks=bool(subtasks))
    
    # Hard stop at max iterations
    if iteration >= max_iterations:
        logger.info("lead_hunter_max_iterations_reached")
        return END
    
    # No new work to do
    if not subtasks:
        logger.info("lead_hunter_no_subtasks")
        return END
    
    # Continue to next iteration
    logger.info("lead_hunter_continuing", next_iteration=iteration)
    return "gate"
```

---

### 4. State Schema Update

**File:** `backend/graph/state.py`

```python
from typing import TypedDict, List, Optional

class AgentState(TypedDict, total=False):
    # ... existing fields ...
    
    # NEW: Iteration tracking
    iteration: int  # Current iteration number (0, 1, 2)
    
    # NEW: Lead Hunter output
    lead_hunter_report: str  # Markdown synthesis report
```

---

## Testing Strategy

### Unit Tests

**File:** `tests/unit/test_lead_hunter.py`

```python
import pytest
from backend.agents.lead_hunter import (
    parse_lead_hunter_response,
    build_lead_hunter_context,
    generate_lead_hunter_markdown
)

def test_parse_lead_hunter_response():
    """Test JSON extraction from LLM response"""
    response = '''Here is my analysis:
    ```json
    {
        "summary": "Test summary",
        "decision": "continue",
        "subtasks": []
    }
    ```
    '''
    result = parse_lead_hunter_response(response)
    assert result["decision"] == "continue"

def test_build_context_formatting():
    """Test context builder produces valid prompt"""
    context = build_lead_hunter_context(
        iteration=1,
        max_iterations=3,
        triage={"verdict": "Malicious", "executive_summary": "Test"},
        malware={},
        infra={},
        graph_stats={"nodes": 50},
        uninvestigated=[]
    )
    assert "Current Iteration: 1" in context
    assert "Test" in context
```

### Integration Tests

**File:** `tests/integration/test_lead_hunter_workflow.py`

```python
import pytest
from backend.graph.workflow import build_graph

@pytest.mark.asyncio
async def test_single_iteration_workflow():
    """Test: Triage → Specialists → Lead Hunter → END"""
    graph = build_graph()
    
    initial_state = {
        "job_id": "test_001",
        "ioc": "google.com",
        "ioc_type": "domain",
        "subtasks": [],
        "iteration": 0
    }
    
    result = await graph.ainvoke(initial_state)
    
    # Verify lead hunter ran
    assert "lead_hunter_report" in result
    # Verify workflow ended (no new subtasks)
    assert result["subtasks"] == []

@pytest.mark.asyncio
async def test_multi_iteration_loop():
    """Test: Multiple iterations with lead hunter creating new tasks"""
    # Mock lead hunter to create subtasks
    # Verify loop back to gate
    # Verify max 3 iterations enforced
    pass
```

### End-to-End Tests

**Test Case 1: Simple Single Iteration**
- Input: Known benign domain
- Expected: Triage → No malicious findings → Specialists report benign → Lead hunter decides END

**Test Case 2: Multi-Stage Malware**
- Input: Dropper hash
- Expected:
  - Iteration 0: Triage finds dropper
  - Iteration 1: Malware analyzes dropper, finds C2 + payload
  - Lead hunter creates tasks for C2 and payload
  - Iteration 2: Specialists analyze C2 + payload
  - Lead hunter decides END (chain complete)

**Test Case 3: Max Iterations**
- Input: Complex APT infrastructure
- Expected: Runs exactly 3 iterations, then forced END

---

## Deployment Checklist

- [ ] Create `backend/agents/lead_hunter.py`
- [ ] Add `get_uninvestigated_nodes()` to `InvestigationCache`
- [ ] Update `backend/graph/workflow.py` with new nodes and routing
- [ ] Add `iteration` and `lead_hunter_report` fields to `AgentState`
- [ ] Create unit tests
- [ ] Create integration tests
- [ ] Deploy to Cloud Run
- [ ] Test with known malware samples
- [ ] Update frontend to display lead hunter report
- [ ] Monitor Cloud logs for iteration behavior
- [ ] Document findings

---

## Success Metrics

1. **Iteration Loop Functions**: Graph executes 1-3 iterations based on findings
2. **Graph Expansion**: Node count grows with each iteration
3. **Intelligent Prioritization**: Lead hunter focuses on malicious entities
4. **Holistic Reports**: Synthesis report tells complete attack narrative
5. **Resource Management**: Stops at 3 iterations or when investigation complete

---

## Known Limitations & Future Work

### Current Limitations
- Fixed max iterations (3) - could be made configurable
- No cost-based stopping (e.g., when GTI API quota running low)
- LLM might hallucinate entities not in graph
- No support for "pause and resume" investigation

### Future Enhancements (Phase 5.3+)
- **Adaptive Iterations**: Let LLM decide iteration limit based on complexity
- **Cost Awareness**: Factor in API quota when deciding to continue
- **Hunt Package Generation**: Auto-create YARA/Sigma rules from findings
- **Timeline Reconstruction**: Chronological attack timeline visualization
- **Collaborative Mode**: Allow analyst to inject manual tasks mid-investigation
