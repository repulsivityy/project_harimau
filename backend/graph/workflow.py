from langgraph.graph import StateGraph, END
from backend.graph.state import AgentState
from backend.agents.triage import triage_node
from backend.utils.logger import get_logger

logger = get_logger("workflow_graph")

def build_graph():
    """
    Constructs the Harimau Investigation Graph.
    MVP: Start -> Triage -> End
    """
    logger.info("building_graph")
    
    # 1. Initialize Graph
    workflow = StateGraph(AgentState)
    
    # 2. Add Nodes
    workflow.add_node("triage", triage_node)
    
    # 3. Add Edges
    workflow.set_entry_point("triage")
    
    # Logic for routing typically goes here (conditional edges)
    # For MVP (Phase 2), we just end after triage.
    workflow.add_edge("triage", END)
    
    # 4. Compile
    return workflow.compile()

# Singleton instance of the runnable graph
app_graph = build_graph()
