"""
Data Models for Threat Hunter Platform
"""

import time
from typing import TypedDict, Optional, List, Dict, Any
from pydantic import BaseModel, Field



def check_budget(budget: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Check if investigation can continue (helper for dict-based budget).
    """
    # Limits
    max_api_calls = budget.get("max_api_calls", 200)
    max_graph_nodes = budget.get("max_graph_nodes", 50)
    max_wall_time = budget.get("max_wall_time", 600)
    
    # Counters
    api_calls_made = budget.get("api_calls_made", 0)
    nodes_created = budget.get("nodes_created", 0)
    start_time = budget.get("start_time", time.time())
    
    # Check API call limit
    if api_calls_made >= max_api_calls:
        return False, f"API call limit reached ({api_calls_made}/{max_api_calls})"
    
    # Check graph node limit
    if nodes_created >= max_graph_nodes:
        return False, f"Graph node limit reached ({nodes_created}/{max_graph_nodes})"
    
    # Check wall time limit
    elapsed = time.time() - start_time
    if elapsed >= max_wall_time:
        return False, f"Investigation timeout ({int(elapsed)}s/{max_wall_time}s)"
    
    return True, None

class InvestigationState(TypedDict):
    """LangGraph state for investigations"""
    
    # Input
    ioc: str
    ioc_type: str
    
    # Graph (serialized as lists)
    graph_nodes: List[Dict[str, Any]]
    graph_edges: List[Dict[str, Any]]
    
    # Control flow
    iteration: int
    max_iterations: int
    agents_run: List[str]
    status: str
    verdict: str  # For routing decisions
    
    # Budget tracking (Stored as dict for JSON compatibility)
    budget: Dict[str, Any]
    
    # Output
    findings: List[Dict[str, Any]]
    report: str
