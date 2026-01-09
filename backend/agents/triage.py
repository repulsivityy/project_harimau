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

# Triage Prompt (Enhanced to force tool usage)
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

**MANDATORY TOOL USAGE:**
You **MUST** call the `get_relationships` tool AT LEAST ONCE before generating your final output.
- For IPs: Check 'resolutions' AND 'communicating_files'
- For Domains: Check 'resolutions' AND 'referrer_files'  
- For Files: Check 'contacted_ips' AND 'contacted_domains'
- For all types: Check 'associations'

Do NOT skip this step. Even if the base verdict seems clear, relationships provide critical context.

**Output Format (JSON ONLY):**
After gathering relationship data, output ONLY this JSON structure (no preamble):
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

    # GTI Assessment
    triage_data["threat_score"] = get_val(data, "attributes.gti_assessment.threat_score.value")
    triage_data["verdict"] = get_val(data, "attributes.gti_assessment.verdict.value")
    triage_data["description"] = get_val(data, "attributes.gti_assessment.description")

    return triage_data


async def triage_node(state: AgentState):
    """
    Hybrid Triage Agent with guaranteed relationship fetching.
    1. Python Layer: Regex ID + Fetch Base Report + Extract Meta.
    2. Agent Layer: LLM with Tools (Manual Loop with forced execution).
    """
    ioc = state["ioc"]
    logger.info("triage_start", ioc=ioc)
    
    # 1. Identification (Python)
    ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    config = {}
    
    if "http" in ioc or "/" in ioc:
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
        
        base_data = await config["direct_tool"](ioc)
        
        if not base_data or "data" not in base_data:
             logger.warning("triage_direct_api_empty", ioc=ioc)
             base_data = {"id": ioc}
        else:
             base_data = base_data["data"]

        # Extract Facts
        triage_data = extract_triage_data(base_data, config["type"])
        
        # Initialize metadata with relationships dict
        state["metadata"]["risk_level"] = "Assessing..." 
        state["metadata"]["gti_score"] = triage_data["threat_score"] or "N/A"
        state["metadata"]["rich_intel"] = triage_data
        state["metadata"]["rich_intel"]["relationships"] = {}  # Pre-initialize
        
        async with mcp_manager.get_session("gti") as session:
            # --- 3. Define Relationship Tool ---
            from langchain_core.tools import tool
            from langchain_core.messages import ToolMessage
            
            @tool
            async def get_relationships(relationship_name: str):
                """
                Fetches entities related to the current IOC. 
                Use this to find campaigns, threat actors, communicating files, or resolutions.
                Valid relationship_names: associations, resolutions, communicating_files, contacted_domains, contacted_ips, referrer_files, subdomains.
                """
                logger.info("triage_agent_invoking_tool", ioc=ioc, rel=relationship_name)
                try:
                    res = await session.call_tool(config["rel_tool"], arguments={
                        config["arg"]: ioc, 
                        "relationship_name": relationship_name, 
                        "descriptors_only": True,
                        "limit": 10
                    })
                    if res.content:
                         return res.content[0].text
                    return "[]"  # Return empty array instead of "No results"
                except Exception as e:
                    logger.error("triage_tool_error", rel=relationship_name, error=str(e))
                    return f'{{"error": "{str(e)}"}}'

            llm_tools = [get_relationships]
            
            # Setup LLM
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            if not project_id:
                raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is missing.")
            
            location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
            llm = ChatVertexAI(
                model="gemini-2.5-flash", 
                temperature=0.0,
                project=project_id, 
                location=location
            ).bind_tools(llm_tools)
            
            messages = [
                SystemMessage(content=TRIAGE_PROMPT),
                HumanMessage(content=f"""
IOC: {ioc}
Type: {config['type']}
Base Report Facts: {json.dumps(triage_data, indent=2)}

NOW: Use the get_relationships tool to fetch related entities BEFORE generating your final JSON.
For {config['type']}, you should check relationships like:
- associations (always useful)
- {'resolutions, communicating_files' if config['type'] in ['IP', 'Domain'] else 'contacted_ips, contacted_domains' if config['type'] == 'File' else 'contacted_domains'}

Start by calling get_relationships now.
                """)
            ]
            
            # --- 4. Manual Tool Execution Loop with Forced Minimum ---
            tool_calls_made = 0
            final_content = ""
            
            for turn in range(5):  # Increased to 5 turns
                logger.info("triage_loop_turn", turn=turn, tools_called=tool_calls_made)
                response = await llm.ainvoke(messages)
                messages.append(response)
                
                if response.tool_calls:
                    # Execute Tools
                    logger.info("triage_executing_tool_calls", count=len(response.tool_calls))
                    for tc in response.tool_calls:
                        if tc["name"] == "get_relationships":
                            tool_calls_made += 1
                            logger.info("triage_invoking_tool", tool=tc["name"], args=tc["args"])
                            
                            res_txt = await get_relationships.ainvoke(tc["args"])
                            logger.info("triage_tool_response", raw_len=len(res_txt))
                            
                            tool_msg = ToolMessage(content=res_txt, tool_call_id=tc["id"])
                            messages.append(tool_msg)
                            
                            # Store in state
                            try:
                                rel_name = tc["args"]["relationship_name"]
                                
                                # Parse response
                                entities = []
                                try:
                                    parsed = json.loads(res_txt)
                                    if isinstance(parsed, dict):
                                        if "error" in parsed:
                                            logger.warning("triage_tool_returned_error", rel=rel_name, error=parsed["error"])
                                            continue
                                        entities = parsed.get("data", [])
                                    elif isinstance(parsed, list):
                                        entities = parsed
                                except json.JSONDecodeError:
                                    logger.warning("triage_tool_output_not_json", raw=res_txt[:200])
                                    continue

                                # Store
                                state["metadata"]["rich_intel"]["relationships"][rel_name] = entities
                                logger.info("triage_stored_relationships", rel=rel_name, count=len(entities))
                                    
                            except Exception as e:
                                logger.error("triage_relationship_storage_failed", error=str(e))
                else:
                    # No more tool calls - check if we've called enough
                    if tool_calls_made == 0:
                        # Force at least one tool call
                        logger.warning("triage_no_tools_called", forcing_prompt=True)
                        messages.append(HumanMessage(content="You have not used the get_relationships tool yet. Please call it now to fetch related entities before generating your final answer."))
                        continue
                    
                    # Agent provided final answer
                    final_content = response.content
                    logger.info("triage_final_answer_received", tools_used=tool_calls_made)
                    break
            
            if not final_content:
                # Fallback
                from langchain_core.messages import AIMessage
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                         final_content = msg.content
                         break
            
            # --- 5. Parse Final Response ---
            try:
                final_text = ""
                if isinstance(final_content, list):
                    for block in final_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            final_text += block.get("text", "")
                        elif isinstance(block, str):
                            final_text += block
                else:
                    final_text = str(final_content)

                # Clean and parse
                clean_content = final_text.replace("```json", "").replace("```", "").strip()
                analysis = json.loads(clean_content)
                
                state["ioc_type"] = analysis.get("ioc_type")
                state["subtasks"] = analysis.get("subtasks", [])
                
                if "summary" in analysis:
                    state["metadata"]["rich_intel"]["triage_summary"] = analysis["summary"]
                
                state["metadata"]["risk_level"] = analysis.get("gti_verdict", "Unknown")
                
                logger.info("triage_agent_success", 
                            risk=state["metadata"]["risk_level"], 
                            subtasks=len(state["subtasks"]),
                            relationships=len(state["metadata"]["rich_intel"]["relationships"]))
                            
            except Exception as e:
                logger.error("triage_parse_fail", error=str(e), raw=str(final_content)[:500])
                state["metadata"]["risk_level"] = "Error"
                
    except Exception as e:
        logger.error("triage_fatal_error", error=str(e))
        state["metadata"]["risk_level"] = "Error"
        
    return state
