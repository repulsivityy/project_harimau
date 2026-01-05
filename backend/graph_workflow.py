"""
Phase 1 Graph Workflow: Triage Only
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.models import InvestigationState
from backend.agents.triage import create_triage_agent
from backend.agents.synthesis import create_synthesis_agent

def create_investigation_graph(logger):
    """
    Create a single-node workflow for Phase 1 (Triage Only).
    """
    workflow = StateGraph(InvestigationState)
    
    # Add Triage Node
    workflow.add_node("triage", create_triage_agent(logger))
    workflow.add_node("synthesis", create_synthesis_agent(logger))
    
    # Entry Point
    workflow.set_entry_point("triage")
    
    # Routing: Triage -> Synthesis -> END
    workflow.add_edge("triage", "synthesis")
    workflow.add_edge("synthesis", END)
    
    return workflow

def compile_workflow(builder, checkpointer=None):
    """Compile the graph with optional checkpointer"""
    from langgraph.checkpoint.memory import MemorySaver
    if checkpointer is None:
        checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)

def create_workflow(logger, checkpointer=None):
    """
    Create and compile the investigation workflow.
    Args:
        logger: Must be an instance of InvestigationLogger
        checkpointer: Optional checkpointer for persistence
    """
    builder = create_investigation_graph(logger)
    return compile_workflow(builder, checkpointer)
