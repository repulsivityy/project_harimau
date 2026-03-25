import json
from langchain_core.messages import SystemMessage, HumanMessage
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache
from backend.graph.state import AgentState

logger = get_logger("agent_lead_hunter_planning")

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
    triage_data = state.get("metadata", {}).get("rich_intel", {})
    specialist_data = state.get("specialist_results", {})

    # 1. Gather Context
    context_str = f"""
    **Triage Context:**
    {str(triage_data.get('triage_analysis', {}).get('executive_summary', 'N/A'))}

    **Specialist Findings (Latest):**
    """
    for agent, res in specialist_data.items():
        context_str += f"- {agent}: {res.get('summary', 'No summary')}\n"

    # 2. Format pre-filtered uninvestigated nodes (passed in from lead_hunter_node)
    try:
        root_ioc = state.get("ioc")
        uninvestigated_leads = [
            f"Type: {n.get('type')} | ID: {n['id']} | Label: {n.get('label', n['id'])}"
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
            content = "".join([
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in response.content
            ])
        else:
            content = str(response.content)
            
        # Initial cleanup
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        return json.loads(content)
    except Exception as e:
        logger.error("lead_hunter_planning_error", error=str(e))
        return {"subtasks": []}
