"""
Graph Utilities - NetworkX Integration
"""

import networkx as nx
from typing import Dict, Any, List

def state_to_networkx(state: Dict[str, Any]) -> nx.DiGraph:
    """
    Convert investigation state to NetworkX graph.
    
    Args:
        state: InvestigationState dict
    
    Returns:
        NetworkX DiGraph
    """
    G = nx.DiGraph()
    
    # Add Nodes
    for node in state.get("graph_nodes", []):
        G.add_node(
            node["id"],
            type=node.get("type"),
            verdict=node.get("verdict"),
            score=node.get("score", 0),
            data=node.get("data", {})
        )
        
    # Add Edges
    for edge in state.get("graph_edges", []):
        G.add_edge(
            edge["source"],
            edge["target"],
            relation=edge.get("relation", "related_to")
        )
        
    return G

def get_graph_stats(G: nx.DiGraph) -> Dict[str, Any]:
    """
    Get basic graph statistics.
    """
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": nx.density(G),
        "components": nx.number_weakly_connected_components(G)
    }
