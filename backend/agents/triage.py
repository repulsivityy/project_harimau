import os
import json
import re


from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI
from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger
import backend.tools.gti as gti

logger = get_logger("agent_triage")

# Triage Prompt (normally loaded from agents.yaml, hardcoded for MVP)
TRIAGE_PROMPT = """
You are a Senior Threat Intelligence Analyst (Triage) with 15 years of experience in a Security Operations Center (SOC).
Your goal is to perform an initial assessment of the provided IOC to determine if it warrants deep investigation.

**Your Persona:**
- You are skeptical, evidence-based, and focused on prioritization.
- You do not make assumptions; you rely strictly on the provided "Rich Intelligence Data".
- You are effective: you only recommend subtasks if there is a clear lead to follow.

**Input Data:**
You have access to "Rich Intelligence Data" from Google Threat Intelligence, including:
1. Basic Report (Verdict, Scores).
2. Advanced Attributes (File metadata, IP details).
3. Relationships (Associations, Resolutions, Communicating entities).

**Analysis Instructions:**
1. **Analyze Facts:** Look at the Threat Score, Verdict, and Associations.
2. **Determine Verdict:** Verdicts should be taken from gti_assessment_verdicts

3. **Determine Next Steps (Routing Logic):**
   - **IF MALICIOUS/SUSPICIOUS FILE**: Route to `malware_specialist` to analyze behavior.
   - **IF MALICIOUS/SUSPICIOUS NETWORK (IP/Domain/URL)**: Route to `infrastructure_specialist` to map infrastructure.
   - **IF BENIGN**: Do NOT generate subtasks. Inform the user and recommend to close the alert.

**CRITICAL INSTRUCTION:**
You **MUST** call the `get_relationships` tool (e.g., for 'resolutions', 'communicating_files', or 'associations') **BEFORE** generating the final JSON output.
- If you see an IP, check `resolutions` or `communicating_files`.
- If you see a Domain, check `subdomains` or `referrer_files`.
- If you see a File, check `contacted_ips`.
**DO NOT** generate the final JSON until you have gathered this evidence.

**Output Format (JSON ONLY):**
{
    "ioc_type": "IP|Domain|File|URL",
    "gti_verdict": "Malicious|Suspicious|Undetected|Benign",
    "gti_score": "...",
    "associations": "...", 
    "summary": "Concise, markdown-formatted assessment. START with the verdict. THEN describe key relationships found (e.g., 'Resolves to malicious domain X', 'Downloads file Y'). END with why the specialist agents are needed.",
    "subtasks": [
        {"agent": "malware_specialist", "task": "Analyze behavior..."},
        {"agent": "infrastructure_specialist", "task": "Map infrastructure..."}
    ]
}
"""


from langchain_core.tools import tool
from langchain_core.messages import ToolMessage

# --- Helpers ---
def extract_triage_data(data: dict, ioc_type: str) -> dict:
    """
    Deterministically extracts 'Triage Data' for the Frontend.
    Handles missing keys gracefully.
    """
    triage_data = {}
    
    # Helper for deep get
    def get_val(d, path):
        keys = path.split('.')
        curr = d
        for k in keys:
            if isinstance(curr, dict):
                curr = curr.get(k)
                if curr is None: return None
            else:
                return None
        return curr
        
    triage_data["id"] = data.get("id")
    triage_data["malicious_stats"] = get_val(data, "attributes.last_analysis_stats.malicious")
    stats = get_val(data, "attributes.last_analysis_stats") or {}
    triage_data["total_stats"] = (
        stats.get("malicious", 0) + 
        stats.get("harmless", 0) + 
        stats.get("suspicious", 0) + 
        stats.get("undetected", 0) + 
        stats.get("timeout", 0)
    )

    # GTI Assessment (Strict Alignment with User Evidence)
    # User's trace shows gti_assessment is inside "attributes"
    triage_data["threat_score"] = get_val(data, "attributes.gti_assessment.threat_score.value")
    triage_data["verdict"] = get_val(data, "attributes.gti_assessment.verdict.value")
    triage_data["description"] = get_val(data, "attributes.gti_assessment.description")

    return triage_data

async def triage_node(state: AgentState):
    """
    Hybrid Triage Agent.
    1. Python Layer: Regex ID + Fetch Base Report + Extract Meta.
    2. Agent Layer: LLM with Tools (Manual Loop) to fetch relationships.
    """
    ioc = state["ioc"]
    logger.info("triage_start", ioc=ioc)
    
    # 1. Identification (Python)
    ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    config = {}
    
    # New Config: Direct Tool (Python) + Rel Tool (MCP)
    if "http" in ioc or "/" in ioc:
        # TODO: URL ID encoding if needed
        config = {"type": "URL", "direct_tool": gti.get_url_report, "rel_tool": "get_entities_related_to_an_url", "arg": "url"}
    elif re.match(ipv4_pattern, ioc):
        config = {"type": "IP", "direct_tool": gti.get_ip_report, "rel_tool": "get_entities_related_to_an_ip_address", "arg": "ip_address"}
    elif "." in ioc:
         config = {"type": "Domain", "direct_tool": gti.get_domain_report, "rel_tool": "get_entities_related_to_a_domain", "arg": "domain"}
    else:
         config = {"type": "File", "direct_tool": gti.get_file_report, "rel_tool": "get_entities_related_to_a_file", "arg": "hash"}
         
    logger.info("triage_detected_type", type=config["type"])
    
    try:
        # --- 2. Fast Facts (Python Direct API) ---
        logger.info("triage_fetching_base_report_direct", type=config["type"])
        
        # Call Direct API
        # tools/gti.py returns dict or {}
        base_data = await config["direct_tool"](ioc)
        
        if not base_data or "data" not in base_data:
             logger.warning("triage_direct_api_empty", ioc=ioc)
             base_data = {"id": ioc} # Fallback skeleton
        else:
             base_data = base_data["data"] # Unwrap "data" key standard in VT API

        # Extract Facts
        triage_data = extract_triage_data(base_data, config["type"])
        
        # Store metadata
        state["metadata"]["risk_level"] = "Assessing..." 
        state["metadata"]["gti_score"] = triage_data["threat_score"] or "N/A"
        state["metadata"]["rich_intel"] = triage_data 

        async with mcp_manager.get_session("gti") as session:
            # --- 3. Agentic Loop (LLM using MCP for Relationships) ---
            
            # Define Tools for LLM (Dynamic Wrappers)
            @tool
            async def get_relationships(relationship_name: str):
                """
                Fetches entities related to the current IOC. 
                Use this to find campaigns, threat actors, communicating files, or resolutions.
                Valid relationship_names: associations, resolutions, communicating_files, contacted_domains, contacted_ips.
                """
                logger.info("triage_agent_invoking_tool", ioc=ioc, rel=relationship_name)
                try:
                    res = await session.call_tool(config["rel_tool"], arguments={
                        config["arg"]: ioc, 
                        "relationship_name": relationship_name, 
                        "descriptors_only": False,
                        "limit": 10
                    })
                    if res.content:
                         return res.content[0].text
                    return "No results."
                except Exception as e:
                    return f"Error: {str(e)}"

            llm_tools = [get_relationships]
            
            # Setup LLM
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
            llm = ChatVertexAI(
                model="gemini-2.5-flash", temperature=0.0,
                project=project_id, location=location
            ).bind_tools(llm_tools)
            
            messages = [
                SystemMessage(content=TRIAGE_PROMPT),
                HumanMessage(content=f"""
IOC: {ioc}
Type: {config['type']}
Base Report Facts: {json.dumps(triage_data, indent=2)}

You have the base report. Now, use tools to fetch relationships to validate the verdict or find connections.
                """)
            ]
            
            # Manual Loop (Max 3 turns)
            final_content = ""
            for turn in range(3):
                response = await llm.ainvoke(messages)
                messages.append(response)
                
                if response.tool_calls:
                    # Execute Tools
                    for tc in response.tool_calls:
                        tool_msg = None
                        if tc["name"] == "get_relationships":
                            res_txt = await get_relationships.ainvoke(tc["args"])
                            tool_msg = ToolMessage(content=res_txt, tool_call_id=tc["id"])
                            # Add to Rich Intel for Graph Pop
                            # Add to Rich Intel for Graph Pop
                            try:
                                # Ensure relationships dict exists
                                if "relationships" not in state["metadata"]["rich_intel"]:
                                    state["metadata"]["rich_intel"]["relationships"] = {}

                                # Try parsing as JSON first
                                entities = []
                                try:
                                    parsed = json.loads(res_txt)
                                    # Handle {"data": [...]} vs [...]
                                    if isinstance(parsed, dict):
                                        entities = parsed.get("data", [])
                                    elif isinstance(parsed, list):
                                        entities = parsed
                                except json.JSONDecodeError:
                                    logger.warning("triage_tool_output_not_json", raw=res_txt[:100])
                                    continue # Skip if not JSON

                                # Store normalized entities
                                state["metadata"]["rich_intel"]["relationships"][tc["args"]["relationship_name"]] = entities
                                logger.info("triage_stored_relationships", 
                                            rel=tc["args"]["relationship_name"], 
                                            count=len(entities))
                                            
                            except Exception as e:
                                logger.error("triage_relationship_storage_failed", error=str(e))
                            
                        if tool_msg:
                             messages.append(tool_msg)
                else:
                    # Final Answer
                    final_content = response.content
                    break
            
            if not final_content and messages[-1].content:
                 final_content = messages[-1].content
            
            # 3. Parse and Update State
            try:
                final_text = ""
                if isinstance(response.content, list):
                    for block in response.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            final_text += block.get("text", "")
                        elif isinstance(block, str):
                            final_text += block
                else:
                    final_text = response.content

                # Simple cleaning of markdown code blocks
                clean_content = final_text.replace("```json", "").replace("```", "").strip()
                analysis = json.loads(clean_content)
                state["ioc_type"] = analysis.get("ioc_type")
                state["subtasks"] = analysis.get("subtasks", [])
                state["metadata"]["risk_level"] = analysis.get("risk_level", "Unknown")
                logger.info("triage_agent_success", risk=state["metadata"]["risk_level"])
            except:
                logger.error("triage_parse_fail", raw=final_content)
                state["metadata"]["risk_level"] = "Error"
                
    except Exception as e:
        logger.error("triage_fatal_error", error=str(e))
        state["metadata"]["risk_level"] = "Error"
        
    return state
