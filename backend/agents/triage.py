import os
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI
from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger

logger = get_logger("agent_triage")

# Triage Prompt (normally loaded from agents.yaml, hardcoded for MVP)
TRIAGE_PROMPT = """
You are a Senior Threat Intelligence Analyst (Triage).
Your goal is to perform an initial assessment of the provided IOC.
You have access to the Google Threat Intelligence tool to perform the initial assessment.

Based on the initial report:
1. Determine the IOC Type (IP, Domain, File Hash, URL).
2. Provide the verdict based on Google Threat Intelligence tool.
3. Recommend NEXT STEPS for specialized agents.

Return your analysis in the following JSON format ONLY:
{
    "ioc_type": "ip|domain|hash|url",
    "gti_verdict": "...",
    "gti_score": "...",
    "malicious_count": "...",
    "attributions": "...",
    "summary": "...",
    "subtasks": [
        {"agent": "malware_specialist", "task": "Analyze behavior..."},
        {"agent": "infrastructure_specialist", "task": "Check passive DNS..."}
    ]
}
"""

async def triage_node(state: AgentState):
    """
    Triage Agent Node.
    1. Fetches basic intel from GTI.
    2. Asks LLM to plan next steps.
    """
    ioc = state["ioc"]
    logger.info("triage_start", ioc=ioc)
    
    intel_summary = "No Intelligence Found"
    
    # 1. Fetch Basic Intel via MCP
    try:
        async with mcp_manager.get_session("gti") as session:
            # We assume a generic 'get_reputation' or investigate tool exists
            # For now, let's try to get a basic report based on IOC type (guessed)
            # In a real scenario, we might use a 'classify_ioc' tool first
            
            # Simple heuristic for tool selection (MVP)
            tool_name = "get_ip_report" if "." in ioc and not "http" in ioc else "get_file_report"
            
            logger.info("triage_calling_tool", tool=tool_name)
            result = await session.call_tool(tool_name, arguments={"ioc": ioc})
            
            if result.content:
                intel_summary = result.content[0].text
                
    except Exception as e:
        logger.error("triage_mcp_error", error=str(e))
        intel_summary = f"Error fetching intel: {str(e)}"

    # 2. Ask LLM (Gemini 2.5 Flash)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")

    llm = ChatVertexAI(
        model="gemini-2.5-flash", 
        temperature=0.0,
        project=project_id,
        location=location
    )
    
    messages = [
        SystemMessage(content=TRIAGE_PROMPT),
        HumanMessage(content=f"IOC: {ioc}\n\nIntelligence Report:\n{intel_summary}")
    ]
    
    response = await llm.ainvoke(messages)
    
    # 3. Parse and Update State
    import json
    try:
        # Simple cleaning of markdown code blocks
        content = response.content.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(content)
        
        state["ioc_type"] = analysis.get("ioc_type")
        state["subtasks"] = analysis.get("subtasks", [])
        
        # Log decision
        logger.info("triage_complete", risk=analysis.get("risk_level"), subtasks=len(state["subtasks"]))
        
    except json.JSONDecodeError:
        logger.error("triage_llm_parse_error", content=response.content)
        # Fallback
        state["subtasks"] = []
        
    return state
