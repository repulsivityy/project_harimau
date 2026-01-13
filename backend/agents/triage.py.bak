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

**Output Format (JSON ONLY):**
After gathering relationship data, output ONLY this JSON structure (no preamble):
{
    "ioc_type": "IP|Domain|File|URL",
    "gti_verdict": "Malicious|Suspicious|Undetected|Benign",
    "gti_score": "...",
    "associations": "...", 
    "summary": "Concise, markdown-formatted assessment. START with the verdict. THEN describe key relationships found.",
    "subtasks": [
        {"agent": "malware_specialist", "task": "Analyze behavior..."},
        {"agent": "infrastructure_specialist", "task": "Map infrastructure..."}
    ]
}
"""


def extract_triage_data(data: dict, ioc_type: str) -> dict:
    """Deterministically extracts 'Triage Data' for the Frontend."""
    triage_data = {}
    
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

    triage_data["threat_score"] = get_val(data, "attributes.gti_assessment.threat_score.value")
    triage_data["verdict"] = get_val(data, "attributes.gti_assessment.verdict.value")
    triage_data["description"] = get_val(data, "attributes.gti_assessment.description")

    return triage_data


def parse_mcp_tool_response(res_txt: str, logger, rel_name: str) -> list:
    """
    Liberal parser that handles multiple MCP tool response formats.
    
    Handles:
    1. {"data": [...]}           - Standard wrapped format
    2. [...]                     - Direct array
    3. {...}                     - Single entity (wraps in array)
    4. {"relationship": [...]}   - Relationship-keyed format
    5. Empty strings, errors, etc.
    
    Returns:
        list: Array of entities (empty list if no valid data)
    """
    if not res_txt or not res_txt.strip():
        logger.warning("parse_mcp_empty_response", rel=rel_name)
        return []
    
    try:
        parsed = json.loads(res_txt)
    except json.JSONDecodeError as e:
        logger.error("parse_mcp_json_error", rel=rel_name, error=str(e), sample=res_txt[:200])
        return []
    
    # Case 1: Already a list - use directly
    if isinstance(parsed, list):
        logger.info("parse_mcp_format", rel=rel_name, format="direct_array", count=len(parsed))
        return parsed
    
    # Case 2: Dict - multiple sub-cases
    if isinstance(parsed, dict):
        # Sub-case 2a: Error response
        if "error" in parsed:
            logger.warning("parse_mcp_error_response", rel=rel_name, error=parsed["error"])
            return []
        
        # Sub-case 2b: Standard wrapper {"data": [...]}
        if "data" in parsed:
            data = parsed["data"]
            if isinstance(data, list):
                logger.info("parse_mcp_format", rel=rel_name, format="wrapped_array", count=len(data))
                return data
            elif isinstance(data, dict):
                # Single entity wrapped in data
                logger.info("parse_mcp_format", rel=rel_name, format="wrapped_single", count=1)
                return [data]
            else:
                logger.warning("parse_mcp_unexpected_data_type", rel=rel_name, type=type(data).__name__)
                return []
        
        # Sub-case 2c: Relationship-keyed format {"associations": [...]}
        if rel_name in parsed and isinstance(parsed[rel_name], list):
            logger.info("parse_mcp_format", rel=rel_name, format="relationship_keyed", count=len(parsed[rel_name]))
            return parsed[rel_name]
        
        # Sub-case 2d: Single entity (has "type" and "id" keys)
        if "type" in parsed and "id" in parsed:
            logger.info("parse_mcp_format", rel=rel_name, format="single_entity", count=1)
            return [parsed]
        
        # Sub-case 2e: Unknown dict structure - try to find any array
        logger.warning("parse_mcp_unknown_dict_format", 
                      rel=rel_name, 
                      keys=list(parsed.keys()),
                      sample=str(parsed)[:200])
        
        for key, value in parsed.items():
            if isinstance(value, list) and len(value) > 0:
                logger.info("parse_mcp_format", rel=rel_name, format="found_array_in_dict", key=key, count=len(value))
                return value
        
        return []
    
    # Case 3: Neither list nor dict
    logger.error("parse_mcp_unexpected_type", rel=rel_name, type=type(parsed).__name__)
    return []


async def triage_node(state: AgentState):
    """
    Hybrid Triage Agent with robust MCP response parsing.
    """
    ioc = state["ioc"]
    logger.info("triage_start", ioc=ioc)
    
    # 1. Identification
    ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    config = {}
    
    if "http" in ioc or "/" in ioc:
        config = {"type": "URL", "direct_tool": gti.get_url_report, 
                 "rel_tool": "get_entities_related_to_an_url", "arg": "url"}
    elif re.match(ipv4_pattern, ioc):
        config = {"type": "IP", "direct_tool": gti.get_ip_report, 
                 "rel_tool": "get_entities_related_to_an_ip_address", "arg": "ip_address"}
    elif "." in ioc:
         config = {"type": "Domain", "direct_tool": gti.get_domain_report, 
                  "rel_tool": "get_entities_related_to_a_domain", "arg": "domain"}
    else:
         config = {"type": "File", "direct_tool": gti.get_file_report, 
                  "rel_tool": "get_entities_related_to_a_file", "arg": "hash"}
         
    logger.info("triage_detected_type", type=config["type"])
    
    try:
        # 2. Fast Facts
        logger.info("triage_fetching_base_report_direct", type=config["type"])
        base_data = await config["direct_tool"](ioc)
        
        if not base_data or "data" not in base_data:
             logger.warning("triage_direct_api_empty", ioc=ioc)
             base_data = {"id": ioc}
        else:
             base_data = base_data["data"]

        triage_data = extract_triage_data(base_data, config["type"])
        
        # Initialize metadata
        state["metadata"]["risk_level"] = "Assessing..." 
        state["metadata"]["gti_score"] = triage_data["threat_score"] or "N/A"
        state["metadata"]["rich_intel"] = triage_data
        state["metadata"]["rich_intel"]["relationships"] = {}
        
        async with mcp_manager.get_session("gti") as session:
            # 3. Define relationship tool
            from langchain_core.tools import tool
            from langchain_core.messages import ToolMessage
            
            @tool
            async def get_relationships(relationship_name: str):
                """Fetches entities related to the current IOC."""
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
                    return "[]"
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

Use get_relationships to fetch related entities before generating your final JSON.
                """)
            ]
            
            # Agent Loop
            tool_calls_made = 0
            final_content = ""
            
            for turn in range(5):
                logger.info("triage_loop_turn", turn=turn, tools_called=tool_calls_made)
                response = await llm.ainvoke(messages)
                messages.append(response)
                
                if response.tool_calls:
                    logger.info("triage_executing_tool_calls", count=len(response.tool_calls))
                    for tc in response.tool_calls:
                        if tc["name"] == "get_relationships":
                            tool_calls_made += 1
                            logger.info("triage_invoking_tool", tool=tc["name"], args=tc["args"])
                            
                            res_txt = await get_relationships.ainvoke(tc["args"])
                            logger.info("triage_tool_response", raw_len=len(res_txt))
                            
                            tool_msg = ToolMessage(content=res_txt, tool_call_id=tc["id"])
                            messages.append(tool_msg)
                            
                            # ✅ USE ROBUST PARSER
                            try:
                                rel_name = tc["args"]["relationship_name"]
                                entities = parse_mcp_tool_response(res_txt, logger, rel_name)
                                
                                if entities:
                                    state["metadata"]["rich_intel"]["relationships"][rel_name] = entities
                                    logger.info("triage_stored_relationships", rel=rel_name, count=len(entities))
                                else:
                                    logger.info("triage_no_entities_found", rel=rel_name)
                                    
                            except Exception as e:
                                logger.error("triage_relationship_storage_failed", error=str(e))
                else:
                    if tool_calls_made == 0:
                        logger.warning("triage_no_tools_called", forcing_prompt=True)
                        messages.append(HumanMessage(
                            content="You have not used the get_relationships tool yet. "
                                    "Please call it now to fetch related entities."
                        ))
                        continue
                    
                    final_content = response.content
                    logger.info("triage_final_answer_received", tools_used=tool_calls_made)
                    break
            
            if not final_content:
                from langchain_core.messages import AIMessage
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                         final_content = msg.content
                         break
            
            # Parse final response
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