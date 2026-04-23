import json
from langchain_core.messages import SystemMessage, HumanMessage
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache
from backend.graph.state import AgentState

logger = get_logger("agent_lead_hunter_planning")


def _format_lead_for_prompt(node: dict) -> str:
    """Render a cache node into a planner-friendly one-line lead summary."""
    node_id = node.get("id", "unknown")
    entity_type = node.get("entity_type", "unknown")

    if entity_type == "file":
        label = node.get("meaningful_name") or (node.get("names") or [node_id])[0]
    elif entity_type == "url":
        label = node.get("last_final_url") or node.get("url") or node_id
    elif entity_type == "domain":
        label = node.get("host_name") or node_id
    else:
        label = node.get("name") or node.get("title") or node_id

    context_bits = []
    if node.get("malware_context"):
        context_bits.append(f"malware_context={node['malware_context']}")
    if node.get("infra_context"):
        context_bits.append(f"infra_context={node['infra_context']}")

    gti_assessment = node.get("gti_assessment") or {}
    verdict = gti_assessment.get("verdict") or {}
    threat_score = gti_assessment.get("threat_score") or {}
    if isinstance(verdict, dict) and verdict.get("value"):
        context_bits.append(f"verdict={verdict['value']}")
    if isinstance(threat_score, dict) and threat_score.get("value") is not None:
        context_bits.append(f"threat_score={threat_score['value']}")

    suffix = f" | Context: {', '.join(context_bits)}" if context_bits else ""
    return f"Type: {entity_type} | ID: {node_id} | Label: {label}{suffix}"

# --- PROMPT: ITERATIVE PLANNING ---
LEAD_HUNTER_PLANNING_PROMPT = """
You are the Lead Threat Hunter orchestrating an active investigation.

**Role:**
You are directing a team of specialist agents (Malware Specialist and Infrastructure Specialist).
You have just received their reports from the current round of analysis.
Your job is to determine **what to do next**. You must analyze the current findings and the investigation graph to identify **Intelligence Gaps** and high-priority leads that need further investigation.

**Goal:**
Generate a list of **specific subtasks** for your specialists to execute in the next round.
Focus on **High Confidence Leads** derived from the current findings, such as:
1.  **Dropped Files:** If the Malware Specialist found a dropped file hash that hasn't been analyzed, task the Malware Specialist to analyze it.
2.  **Contacted Infrastructure:** If a file contacts an IP/Domain that hasn't been investigated, task the Infrastructure Specialist.
3.  **Downloaded Files:** If the Infrastructure Specialist found an IP serving a file, task the Malware Specialist.
4.  **Communicating Files:** If an IP is communicating with other known files, task the Malware Specialist.

**Inputs:**
1.  **Triage/Previous Context**: What we knew at the start.
2.  **Specialist Findings (Current Round)**: What the agents just found.
3.  **Uninvestigated Graph Nodes**: A text list of entities found in the graph that have NOT been analyzed yet.

**Instructions:**
- Review the "Uninvestigated Graph Nodes".
- Select the most relevant entities that will help complete the attack picture.
- Do **NOT** re-assign tasks for entities that have already been fully analyzed (unless you have a specific new question).
- Assign `malware_specialist` for Files/Hashes.
- Assign `infrastructure_specialist` for IPs, Domains, URLs.
- Provide clear `context` for why this task is important (e.g., "This file was dropped by the initial sample").

**Output Format (JSON):**
Return a JSON object containing a list of subtasks.
{
    "subtasks": [
        {
            "agent": "malware_specialist",
            "entity_id": "hash_of_dropped_file",
            "task": "Analyze dropped file behavior and capabilities",
            "context": "File was dropped by initial payload <original_hash>"
        },
        {
            "agent": "infrastructure_specialist",
            "entity_id": "1.2.3.4",
            "task": "Investigate C2 IP address",
            "context": "Initial payload communicates with this IP"
        }
    ],
    "investigation_complete": false,
    "comment": "Brief reasoning for these tasks (optional)"
}

**Constraint:**
- Return ONLY valid JSON.
- If there are NO high-value leads left, return `{"subtasks": [], "investigation_complete": true}`.
- Set `"investigation_complete": true` if you believe the investigation has reached sufficient coverage and further pivots are unlikely to yield new intelligence (e.g. only generic CDN IPs remain, all dropped files already analyzed, infrastructure is well-understood).
"""

async def run_planning_phase(state: AgentState, llm, cache: InvestigationCache, actionable_nodes: list):
    """
    Executes the planning phase logic:
    1. Gathers context (Triage + Specialist Reports).
    2. Uses pre-filtered uninvestigated actionable nodes from the caller.
    3. Prompts the LLM to generate new subtasks.
    """
    job_id = state.get("job_id")
    iteration = state.get("iteration", 0)
    logger.info("lead_hunter_planning_start", job_id=job_id, iteration=iteration, actionable_node_count=len(actionable_nodes))

    triage_data = state.get("metadata", {}).get("rich_intel", {})
    specialist_data = state.get("specialist_results", {})

    # 1. Gather Context
    context_str = f"**Triage Context:**\n{str(triage_data.get('triage_analysis', {}).get('executive_summary', 'N/A'))}\n\n"
    context_str += "**Specialist Findings (Latest):**\n"
    for agent, res in specialist_data.items():
        context_str += f"\n#### {agent.replace('_', ' ').title()}:\n"
        context_str += f"Verdict: {res.get('verdict', 'N/A')} | Summary: {res.get('summary', 'No summary')}\n"

        # Network indicators from malware specialist — these are confirmed C2 and need infra investigation
        if res.get("network_indicators"):
            context_str += "Network indicators found (need infrastructure investigation — Shodan/passive DNS not yet run):\n"
            for ind in res["network_indicators"][:15]:
                context_str += f"  - {ind}\n"

        # Related infrastructure from infra specialist — may host malware files
        if res.get("related_indicators"):
            context_str += "Related infrastructure discovered (may serve malicious files):\n"
            for ind in res["related_indicators"][:15]:
                context_str += f"  - {ind}\n"

        # Already-analyzed targets — do not re-task these
        analyzed = res.get("analyzed_targets", [])
        if analyzed:
            ids = [str(t.get("indicator") or t.get("value") or t) if isinstance(t, dict) else str(t) for t in analyzed[:10]]
            ids = [i for i in ids if i]
            if ids:
                context_str += f"Already analyzed (do NOT re-task): {', '.join(ids)}\n"

    # 2. Format pre-filtered uninvestigated nodes (passed in from lead_hunter_node)
    try:
        root_ioc = state.get("ioc")
        uninvestigated_leads = [
            _format_lead_for_prompt(n)
            for n in actionable_nodes
            if n["id"] != root_ioc
        ]

        # Limit leads to prevent exploding context window
        uninvestigated_str = "\n".join(uninvestigated_leads[:50])

        messages = [
            SystemMessage(content=LEAD_HUNTER_PLANNING_PROMPT),
            HumanMessage(content=f"""
Please plan the next steps.

{context_str}

**Potential Leads (Graph Nodes):**
{uninvestigated_str}
            """)
        ]
        
        response = await llm.ainvoke(messages)
        
        # [CRITICAL FIX] ChatVertexAI/ChatGoogleGenerativeAI sometimes returns a list of blocks
        if isinstance(response.content, list):
            parts = []
            for block in response.content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, (dict, list)):
                        parts.append(json.dumps(text))
                    else:
                        parts.append(str(text))
                else:
                    parts.append(str(block))
            content = "".join(parts)
        else:
            content = str(response.content)
            
        # Initial cleanup
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        result = json.loads(content)
        task_count = len(result.get("subtasks", []))
        logger.info("lead_hunter_planning_complete", job_id=job_id, iteration=iteration, task_count=task_count)
        return result
    except Exception as e:
        logger.error("lead_hunter_planning_error", job_id=job_id, iteration=iteration, error=str(e))
        return {"subtasks": []}
