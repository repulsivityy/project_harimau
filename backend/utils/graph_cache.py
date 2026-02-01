"""
NetworkX-based investigation cache for storing full entity context.

This module provides an in-memory graph cache that stores complete entity
attributes from GTI API, enabling:
1. Token-optimized LLM context (query minimal fields)
2. Rich graph visualization (query display fields)
3. Specialist agent efficiency (no re-fetching)
"""

import networkx as nx
from typing import Dict, List, Any, Optional
import json


class InvestigationCache:
    """NetworkX-based cache for investigation entities with full attributes."""
    
    def __init__(self, graph: Optional[nx.MultiDiGraph] = None):
        """
        Initialize investigation cache.
        
        Args:
            graph: Existing NetworkX graph to reuse, or None to create new
        """
        self.graph = graph if graph is not None else nx.MultiDiGraph()
    
    def add_entity(self, entity_id: str, entity_type: str, attributes: Dict[str, Any]):
        """
        Store full entity with all GTI attributes.
        
        Args:
            entity_id: Unique entity identifier (e.g., SHA256, IP, domain)
            entity_type: Entity type (file, ip_address, domain, url, etc.)
            attributes: Complete attributes dictionary from GTI API
        """
        self.graph.add_node(
            entity_id,
            entity_type=entity_type,
            **attributes
        )
    
    def add_relationship(self, source_id: str, target_id: str, rel_type: str, 
                        metadata: Optional[Dict[str, Any]] = None):
        """
        Add relationship edge between entities.
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            rel_type: Relationship type (e.g., contacted_domains, dropped_files)
            metadata: Optional edge metadata
        """
        edge_data = {"relationship": rel_type}
        if metadata:
            edge_data.update(metadata)
        
        self.graph.add_edge(source_id, target_id, **edge_data)
    
    def get_entity_minimal(self, entity_id: str, fields: List[str]) -> Dict[str, Any]:
        """
        Get minimal fields for LLM context (token-optimized).
        
        Args:
            entity_id: Entity ID to query
            fields: List of field names to extract
            
        Returns:
            Dictionary with only requested fields
        """
        if entity_id not in self.graph:
            return {}
        
        node_data = self.graph.nodes[entity_id]
        return {field: node_data.get(field) for field in fields if field in node_data}
    
    def get_entity_full(self, entity_id: str) -> Dict[str, Any]:
        """
        Get full entity with all attributes (for specialists).
        
        Args:
            entity_id: Entity ID to query
            
        Returns:
            Dictionary with all stored attributes
        """
        if entity_id not in self.graph:
            return {}
        
        return dict(self.graph.nodes[entity_id])
    
    def get_neighbors(self, entity_id: str, relationship: Optional[str] = None) -> List[str]:
        """
        Get related entities by relationship type.
        
        Args:
            entity_id: Entity ID to query
            relationship: Optional relationship type filter
            
        Returns:
            List of neighbor entity IDs
        """
        if entity_id not in self.graph:
            return []
        
        neighbors = list(self.graph.neighbors(entity_id))
        
        if relationship:
            # Filter by relationship type
            filtered = []
            for neighbor in neighbors:
                # Check all edges between source and target (MultiDiGraph)
                for edge_key, edge_data in self.graph[entity_id][neighbor].items():
                    if edge_data.get('relationship') == relationship:
                        filtered.append(neighbor)
                        break  # Only add once even if multiple edges
            return filtered
        
        return neighbors
    
    def get_neighbors_with_data(self, entity_id: str, relationship: Optional[str] = None,
                                fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get neighbors with their entity data.
        
        Args:
            entity_id: Entity ID to query
            relationship: Optional relationship type filter
            fields: Optional list of fields to extract (None = all fields)
            
        Returns:
            List of neighbor entity dictionaries
        """
        neighbor_ids = self.get_neighbors(entity_id, relationship)
        
        neighbors_data = []
        for neighbor_id in neighbor_ids:
            if fields:
                entity_data = self.get_entity_minimal(neighbor_id, fields)
            else:
                entity_data = self.get_entity_full(neighbor_id)
            
            if entity_data:
                entity_data["id"] = neighbor_id  # Ensure ID is present
                neighbors_data.append(entity_data)
        
        return neighbors_data
    
    def get_all_entities_by_type(self, entity_type: str) -> List[str]:
        """
        Get all entity IDs of a specific type.
        
        Args:
            entity_type: Type to filter by (file, domain, ip_address, url)
            
        Returns:
            List of entity IDs matching the type
        """
        return [
            node for node, data in self.graph.nodes(data=True)
            if data.get('entity_type') == entity_type
        ]
    
    def has_entity(self, entity_id: str) -> bool:
        """Check if entity exists in cache."""
        return entity_id in self.graph
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        entity_types = {}
        for node, data in self.graph.nodes(data=True):
            etype = data.get('entity_type', 'unknown')
            entity_types[etype] = entity_types.get(etype, 0) + 1
        
        return {
            "total_entities": self.graph.number_of_nodes(),
            "total_relationships": self.graph.number_of_edges(),
            "entity_types": entity_types
        }
        
    def mark_as_investigated(self, entity_id: str, agent: str):
        """
        Mark an entity as investigated by a specific agent.
        
        Args:
            entity_id: The entity ID
            agent: The agent name (e.g., 'malware', 'infrastructure')
        """
        if entity_id not in self.graph:
            return
            
        node = self.graph.nodes[entity_id]
        analyzed_by = set(node.get("analyzed_by", []))
        analyzed_by.add(agent)
        
        # Update node attribute (convert back to list for JSON serialization)
        self.graph.nodes[entity_id]["analyzed_by"] = list(analyzed_by)
        
    def get_uninvestigated_nodes(self, agent_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get nodes that have NOT been fully investigated.
        
        Args:
            agent_filter: If provided, only returns nodes NOT analyzed by this specific agent.
            
        Returns:
            List of node dictionaries with their data.
        """
        uninvestigated = []
        for node_id, data in self.graph.nodes(data=True):
            analyzed_by = data.get("analyzed_by", [])
            
            # If agent_filter is specific, check if THIS agent has analyzed it
            if agent_filter:
                if agent_filter not in analyzed_by:
                    # Return full data
                    node_data = dict(data)
                    node_data["id"] = node_id
                    uninvestigated.append(node_data)
            else:
                # If no filter, return if NO ONE has analyzed it (fresh node)
                if not analyzed_by:
                    node_data = dict(data)
                    node_data["id"] = node_id
                    uninvestigated.append(node_data)
                    
        return uninvestigated

    def export_for_visualization(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Export graph data for frontend visualization.
        
        Returns:
            Dictionary with 'nodes' and 'edges' lists
        """
        nodes = []
        edges = []
        
        # Export nodes
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "type": data.get("entity_type"),
                **{k: v for k, v in data.items() if k != "entity_type"}
            })
        
        # Export edges
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relationship": data.get("relationship"),
                **{k: v for k, v in data.items() if k != "relationship"}
            })
        
        return {"nodes": nodes, "edges": edges}
