import os
from langchain_google_vertexai import ChatVertexAI
from backend.config import DEFAULT_HUNT_ITERATIONS
from backend.graph.state import AgentState
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache

from backend.agents.lead_hunter_planning import run_planning_phase
from backend.agents.lead_hunter_synthesis import generate_final_report_llm

logger = get_logger("agent_lead_hunter")

ACTIONABLE_TYPES = {"file", "ip_address", "domain", "url"}


async def lead_hunter_node(state: AgentState):
    """
    Lead Threat Hunter Node.
    - Iteration < Max: Plan next steps (generate subtasks).
    - Iteration >= Max OR early exit condition met: Synthesize final report.

    Early exit conditions (in order):
      Layer 1 - No uninvestigated actionable nodes remain (zero-cost, no LLM call).
      Layer 2 - LLM signals investigation_complete in its planning response.
      Layer 3 - New subtasks are a subset of previously tasked entities (convergence).
    """
    logger.info("lead_hunter_start", iteration=state.get("iteration"))

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")

    # Flash for planning (fast, cost-efficient), Pro only for final synthesis
    llm_flash = ChatVertexAI(
        model="gemini-2.5-flash",
        temperature=0.1,
        project=project_id,
        location=location,
    )
    llm_pro = ChatVertexAI(
        model="gemini-2.5-pro",
        temperature=0.1,
        project=project_id,
        location="global",
    )

    # Initialize Cache to read graph state
    cache = InvestigationCache(state.get("investigation_graph"))

    # --- DETERMINE MODE ---
    current_iteration = state.get("iteration", 0)
    MAX_ITERATIONS = state.get("max_iterations", DEFAULT_HUNT_ITERATIONS)

    if current_iteration < MAX_ITERATIONS:
        # --- LAYER 1: Pre-check uninvestigated nodes (no LLM call needed) ---
        uninvestigated = cache.get_uninvestigated_nodes()
        actionable = [n for n in uninvestigated if n.get("type") in ACTIONABLE_TYPES]

        if not actionable:
            logger.info("lead_hunter_early_exit", reason="no_uninvestigated_nodes", iteration=current_iteration)
        else:
            # --- PLANNING MODE (uses Flash) ---
            logger.info("lead_hunter_mode_planning", actionable_count=len(actionable))

            plan = await run_planning_phase(state, llm_flash, cache, actionable)
            new_subtasks = plan.get("subtasks", [])

            # --- LAYER 2: LLM confidence signal ---
            if plan.get("investigation_complete"):
                logger.info("lead_hunter_early_exit", reason="llm_signals_complete", iteration=current_iteration)
                new_subtasks = []

            if new_subtasks:
                # --- LAYER 3: Convergence detection ---
                prev_tasked = set(state.get("tasked_entities", []))
                new_entity_ids = {t["entity_id"] for t in new_subtasks}

                if new_entity_ids and new_entity_ids.issubset(prev_tasked):
                    logger.info("lead_hunter_early_exit", reason="convergence", entities=list(new_entity_ids))
                else:
                    logger.info("lead_hunter_new_tasks", count=len(new_subtasks))
                    state["subtasks"] = new_subtasks
                    state["iteration"] = current_iteration + 1
                    state["tasked_entities"] = list(new_entity_ids)
                    return state

            logger.info("lead_hunter_no_new_tasks", reason="empty_subtasks_or_converged")

    # --- SYNTHESIS MODE (uses Pro) ---
    logger.info("lead_hunter_mode_synthesis")

    final_report = await generate_final_report_llm(state, llm_pro)
    state["final_report"] = final_report

    # [CRITICAL] CLEAR SUBTASKS TO STOP INFINITE LOOP
    state["subtasks"] = []

    return state
