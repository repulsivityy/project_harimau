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
    "comment": "Brief reasoning for these tasks (optional)"
}

**Constraint:**
- Return ONLY valid JSON.
- If there are NO high-value leads left, return `{"subtasks": []}`.
"""

async def run_planning_phase(state: AgentState, llm, cache: InvestigationCache):
    """
    Executes the planning phase logic:
    1. Gathers context (Triage + Specialist Reports).
    2. Identifies uninvestigated nodes from the graph.
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

    # 2. Identify Uninvestigated Nodes from Graph
    try:
        # Get all nodes
        graph_data = cache.export_for_visualization()
        all_nodes = graph_data.get("nodes", [])
        
        uninvestigated_leads = []
        
        # Simple heuristic to identify candidates
        # We rely on the Lead Hunter LLM to filter out duplicates or items already in context
        # if we don't track 'investigated' flags perfectly yet.
        
        for node in all_nodes:
            nid = node["id"]
            ntype = node.get("type", "unknown")
            
            # Skip the root IOC itself (usually starting point)
            if nid == state.get("ioc"): continue
            
            # Filter for interesting types suitable for specialists
            if ntype in ["file", "ip_address", "domain", "url"]:
                 uninvestigated_leads.append(f"Type: {ntype} | ID: {nid} | Label: {node.get('label')}")

        # Limit leads to prevent exploding context window
        # Prioritize recent adds? For now, just slice.
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
        content = response.content
        
        # Initial cleanup
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        return json.loads(content)
    except Exception as e:
        logger.error("lead_hunter_planning_error", error=str(e))
        return {"subtasks": []}
