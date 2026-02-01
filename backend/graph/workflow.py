from langgraph.graph import StateGraph, END
from backend.graph.state import AgentState
from backend.agents.triage import triage_node
from backend.agents.malware import malware_node
from backend.agents.infrastructure import infrastructure_node
from backend.utils.logger import get_logger

logger = get_logger("workflow_graph")

from backend.agents.infrastructure import infrastructure_node

def build_graph():
    """
    Constructs the Harimau Investigation Graph.
    Phase 5.1: Triage -> Parallel Specialists (Gate) -> End
    """
    logger.info("building_graph")
    
    # 1. Initialize Graph
    workflow = StateGraph(AgentState)
    
    # 2. Add Nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("malware_specialist", malware_node)
    workflow.add_node("infrastructure_specialist", infrastructure_node)
    
    # 3. Add Edges
    workflow.set_entry_point("triage")
    
    def route_from_triage(state: AgentState):
        """
        Routes to specialist agents based on subtasks.
        Returns a LIST of nodes to execute in parallel.
        """
        subtasks = state.get("subtasks", [])
        next_nodes = []
        
        # Check subtasks
        for task in subtasks:
            agent = task.get("agent")
            if agent in ["malware_specialist", "malware"]:
                 if "malware_specialist" not in next_nodes:
                     next_nodes.append("malware_specialist")
            elif agent in ["infrastructure_specialist", "infrastructure"]:
                 if "infrastructure_specialist" not in next_nodes:
                     next_nodes.append("infrastructure_specialist")
        
        if not next_nodes:
            return END
            
        next_nodes = []
        for task in subtasks:
            agent = task.get("agent")
            if agent in ["malware_specialist", "malware"] and "malware_specialist" not in next_nodes:
                next_nodes.append("malware_specialist")
            elif agent in ["infrastructure_specialist", "infrastructure"] and "infrastructure_specialist" not in next_nodes:
                next_nodes.append("infrastructure_specialist")
                
        return next_nodes if next_nodes else END

    # Conditional Routing (Parallel Fan-Out)
    workflow.add_conditional_edges(
        "triage",
        route_from_triage,
        {
            "malware_specialist": "malware_specialist",
            "infrastructure_specialist": "infrastructure_specialist",
            END: END
        }
    )
    
    # Specialists -> End (Fan-In/Converge)
    workflow.add_edge("malware_specialist", END)
    workflow.add_edge("infrastructure_specialist", END)
    
    # 4. Compile
    return workflow.compile()

# Singleton instance of the runnable graph
app_graph = build_graph()
