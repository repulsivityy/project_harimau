import os
from langchain_google_vertexai import ChatVertexAI
#from langchain_google_genai import ChatGoogleGenerativeAI # preperation for migration
from backend.graph.state import AgentState
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache

from backend.agents.lead_hunter_planning import run_planning_phase
from backend.agents.lead_hunter_synthesis import generate_final_report_llm

logger = get_logger("agent_lead_hunter")

async def lead_hunter_node(state: AgentState):
    """
    Lead Threat Hunter Node.
    - Iteration < Max: Plan next steps (generate subtasks).
    - Iteration >= Max: Synthesize final report.
    """
    logger.info("lead_hunter_start", iteration=state.get("iteration"))
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
    
    llm = ChatVertexAI(
        model="gemini-2.5-pro",
        temperature=0.1, # Slightly creative for writing/planning
        project=project_id,
        location="global" # Using global endpoint for Gemini 2.5 Pro
    )
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-pro-preview",
        project=project_id,
    )
    """
    # Initialize Cache to read graph state
    cache = InvestigationCache(state.get("investigation_graph"))
    
    # --- DETERMINE MODE ---
    current_iteration = state.get("iteration", 0)
    
    # Max iterations is controlled by workflow.py (hunt_iterations), 
    MAX_ITERATIONS = 3 
    
    if current_iteration < MAX_ITERATIONS:
        # --- PLANNING MODE ---
        logger.info("lead_hunter_mode_planning")
        
        # Execute logic from 'lead_hunter_planning.py'
        plan = await run_planning_phase(state, llm, cache)
        new_subtasks = plan.get("subtasks", [])
        
        if new_subtasks:
            logger.info("lead_hunter_new_tasks", count=len(new_subtasks))
            
            # Update state with new tasks
            state["subtasks"] = new_subtasks
            state["iteration"] = current_iteration + 1
            
            return state
        else:
            logger.info("lead_hunter_no_new_tasks", reason="LLM returned empty list")
            # If no new tasks, fall through to synthesis immediately
            
    # --- SYNTHESIS MODE ---
    logger.info("lead_hunter_mode_synthesis")
    
    # Execute logic from 'lead_hunter_synthesis.py'
    final_report = await generate_final_report_llm(state, llm)
    state["final_report"] = final_report
    
    # [CRITICAL] CLEAR SUBTASKS TO STOP INFINITE LOOP
    state["subtasks"] = []
    
    return state
