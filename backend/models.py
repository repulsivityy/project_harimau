"""
Data Models for Threat Hunter Platform
"""

from typing import TypedDict, Optional
from dataclasses import dataclass, field
import time


class InvestigationState(TypedDict):
    """LangGraph state for investigations"""
    
    # Input
    ioc: str
    ioc_type: str
    
    # Graph (serialized as lists)
    graph_nodes: list[dict]
    graph_edges: list[dict]
    
    # Control flow
    iteration: int
    max_iterations: int
    agents_run: list[str]
    status: str
    verdict: str  # For routing decisions
    
    # Budget tracking
    budget: 'InvestigationBudget'
    
    # Output
    findings: list[dict]
    report: str


@dataclass
class InvestigationBudget:
    """
    Track and enforce resource limits during investigation.
    
    Prevents:
    - Infinite loops (max iterations)
    - Graph explosions (max nodes)
    - API cost explosions (max API calls)
    - Hung investigations (max wall time)
    """
    
    # Limits
    max_api_calls: int = 200
    max_graph_nodes: int = 50
    max_wall_time: int = 600  # 10 minutes in seconds
    
    # Counters
    api_calls_made: int = 0
    nodes_created: int = 0
    start_time: float = field(default_factory=time.time)
    
    def can_continue(self) -> tuple[bool, Optional[str]]:
        """
        Check if investigation can continue.
        
        Returns:
            Tuple of (can_continue, reason)
            - can_continue: True if investigation can proceed
            - reason: If False, explanation of why it cannot continue
        """
        
        # Check API call limit
        if self.api_calls_made >= self.max_api_calls:
            return False, f"API call limit reached ({self.api_calls_made}/{self.max_api_calls})"
        
        # Check graph node limit
        if self.nodes_created >= self.max_graph_nodes:
            return False, f"Graph node limit reached ({self.nodes_created}/{self.max_graph_nodes})"
        
        # Check wall time limit
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_wall_time:
            return False, f"Investigation timeout ({int(elapsed)}s/{self.max_wall_time}s)"
        
        return True, None
    
    def to_dict(self) -> dict:
        """Serialize budget for logging"""
        elapsed = int(time.time() - self.start_time)
        
        return {
            "api_calls": f"{self.api_calls_made}/{self.max_api_calls}",
            "nodes": f"{self.nodes_created}/{self.max_graph_nodes}",
            "elapsed": f"{elapsed}s/{self.max_wall_time}s",
            "can_continue": self.can_continue()[0]
        }
