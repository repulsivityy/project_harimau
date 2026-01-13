from langgraph.graph import StateGraph, END
from backend.graph.state import AgentState
from backend.agents.triage import triage_node
from backend.agents.malware import malware_node
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
    workflow.add_node("malware_specialist", malware_node)
    
    # 3. Add Edges
    workflow.set_entry_point("triage")
    
    def route_from_triage(state: AgentState):
        """Routes to specialist agents based on subtasks."""
        subtasks = state.get("subtasks", [])
        if not subtasks:
            return END
            
        # Check for first available specialist task
        # Current logic: Prioritize Malware
        for task in subtasks:
            if task.get("agent") in ["malware_specialist", "malware"]:
                return "malware_specialist"
                
        return END

    # Conditional Routing
    workflow.add_conditional_edges(
        "triage",
        route_from_triage,
        {
            "malware_specialist": "malware_specialist",
            END: END
        }
    )
    
    # Analyze -> End
    workflow.add_edge("malware_specialist", END)
    
    # 4. Compile
    return workflow.compile()

# Singleton instance of the runnable graph
app_graph = build_graph()
