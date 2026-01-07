import os
import shutil
import logging
from typing import Dict, Any, List, Optional
import kuzu

logger = logging.getLogger(__name__)

class KuzuGraphManager:
    def __init__(self, db_path: str, clear_existing: bool = False):
        """
        Initialize KuzuDB manager.
        """
        self.db_path = db_path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
        if clear_existing and os.path.exists(db_path):
            try:
                shutil.rmtree(db_path)
                logger.info(f"Cleared existing KuzuDB at {db_path}")
            except Exception as e:
                logger.warning(f"Failed to clear KuzuDB: {e}")
        
        try:
            self.db = kuzu.Database(db_path)
            self.conn = kuzu.Connection(self.db)
            self.init_schema()
            logger.info(f"KuzuDB initialized at {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize KuzuDB: {e}")
            raise e

    def init_schema(self):
        """
        Initialize the graph schema.
        We use a single 'IOC' node table for flexibility and a generic 'REL' edge table.
        """
        # Create IOC Node Table
        try:
            # Check if table exists (simple try-except as check methods vary)
            # Schema: id (PK), type, label, score, verdict
            self.conn.execute("""
                CREATE NODE TABLE IOC (
                    id STRING,
                    type STRING,
                    label STRING,
                    score INT64,
                    verdict STRING,
                    malicious_votes INT64,
                    total_votes INT64,
                    PRIMARY KEY (id)
                )
            """)
            logger.info("Created node table: IOC")
        except RuntimeError as e:
             if "already exists" not in str(e).lower():
                 logger.warning(f"Error creating IOC table (might exist): {e}")

        # Create REL Edge Table
        try:
            # Schema: FROM IOC TO IOC, type, description
            self.conn.execute("""
                CREATE REL TABLE REL (
                    FROM IOC TO IOC,
                    type STRING,
                    description STRING
                )
            """)
            logger.info("Created edge table: REL")
        except RuntimeError as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Error creating REL table (might exist): {e}")

    def add_node(self, node_data: Dict[str, Any]):
        """
        Add or update a node in the graph.
        node_data must contain 'id'.
        """
        if "id" not in node_data:
            logger.error("Node data missing 'id'")
            return

        try:
            # MERGE behavior: If exists, update. If not, create.
            # Kuzu MERGE syntax: MERGE (n:IOC {id: $id}) ON CREATE SET ... ON MATCH SET ...
            # Note: Parameter binding ($id) is recommended.
            
            query = """
                MERGE (n:IOC {id: $id})
                ON CREATE SET 
                    n.type = $type, 
                    n.label = $label, 
                    n.score = $score, 
                    n.verdict = $verdict,
                    n.malicious_votes = $malicious_votes,
                    n.total_votes = $total_votes
                ON MATCH SET
                    n.score = $score,
                    n.verdict = $verdict,
                    n.malicious_votes = $malicious_votes,
                    n.total_votes = $total_votes
            """
            
            params = {
                "id": node_data["id"],
                "type": node_data.get("type", "unknown"),
                "label": node_data.get("label", node_data["id"]),
                "score": int(node_data.get("score", 0)),
                "verdict": node_data.get("verdict", "unknown"),
                "malicious_votes": int(node_data.get("malicious_votes", 0)),
                "total_votes": int(node_data.get("total_votes", 0))
            }
            
            self.conn.execute(query, params)
            
        except Exception as e:
            logger.error(f"Failed to add node {node_data['id']}: {e}")

    def add_edge(self, source_id: str, target_id: str, edge_type: str, description: str = ""):
        """
        Add a relationship between two nodes.
        Nodes should ideally exist, but we can try to merge them if consistent.
        For now, we assume nodes are added before edges.
        """
        try:
            query = """
                MATCH (s:IOC {id: $source_id}), (t:IOC {id: $target_id})
                MERGE (s)-[r:REL {type: $type}]->(t)
                ON CREATE SET r.description = $desc
                ON MATCH SET r.description = $desc
            """
            
            params = {
                "source_id": source_id,
                "target_id": target_id,
                "type": edge_type,
                "desc": description
            }
            
            self.conn.execute(query, params)
            
        except Exception as e:
            logger.error(f"Failed to add edge {source_id} -> {target_id}: {e}")
            
    def get_stats(self) -> Dict[str, int]:
        """Return graph statistics"""
        try:
            num_nodes = self.conn.execute("MATCH (n:IOC) RETURN count(n)").get_next()[0]
            num_edges = self.conn.execute("MATCH ()-[r:REL]->() RETURN count(r)").get_next()[0]
            return {"nodes": num_nodes, "edges": num_edges}
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"nodes": 0, "edges": 0}

    def close(self):
        """Close connection (if needed explicitly)"""
        # Kuzu handles this, but good for cleanup hooks
        pass
