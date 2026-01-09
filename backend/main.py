import os
import json
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from backend.utils.logger import configure_logger, get_logger
from backend.graph.workflow import app_graph

# 1. Configure Logging
configure_logger()
logger = get_logger("backend-api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("backend_startup", status="started")
    yield
    # Shutdown
    logger.info("backend_shutdown", status="stopped")

app = FastAPI(title="Harimau Backend", lifespan=lifespan)

# --- Data Models ---
class InvestigationRequest(BaseModel):
    ioc: str

# --- Endpoints ---

@app.get("/health")
async def health_check():
    """
    Simple health check for Cloud Run.
    """
    logger.debug("health_check_called")
    return {"status": "healthy", "service": "backend", "mcp": "embedded"}

@app.get("/")
async def root():
    return {"message": "Harimau V2 Backend Online"}

# Simple In-Memory Persistence for MVP
JOBS = {}

@app.post("/api/investigate")
async def run_investigation(request: InvestigationRequest):
    """
    Triggers the LangGraph investigation workflow.
    """
    job_id = str(uuid.uuid4())
    logger.info("investigation_request", job_id=job_id, ioc=request.ioc)
    
    # Initialize State
    initial_state = {
        "job_id": job_id,
        "ioc": request.ioc,
        "messages": [],
        "subtasks": [],
        "specialist_results": {},
        "metadata": {}
    }
    
    # Initialize Job Status
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "ioc": request.ioc,
        "created_at": "now" # Placeholder
    }
    
    try:
        # Run the Graph (Blocking for MVP)
        final_state = await app_graph.ainvoke(initial_state)
        
        # Update Job
        result = {
            "job_id": job_id,
            "status": "completed",
            "ioc_type": final_state.get("ioc_type"),
            "subtasks": final_state.get("subtasks"),
            "final_report": final_state.get("final_report", "No report generated."),
            "risk_level": final_state.get("metadata", {}).get("risk_level", "Unknown"),
            "gti_score": final_state.get("metadata", {}).get("gti_score", "N/A"),
            "rich_intel": final_state.get("metadata", {}).get("rich_intel", {}),
        }
        JOBS[job_id] = result
        return result
        
    except Exception as e:
        logger.error("investigation_failed", job_id=job_id, error=str(e))
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/investigations/{job_id}")
async def get_investigation(job_id: str):
    """
    Get investigation status and results.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/debug/investigation/{job_id}")
async def debug_investigation(job_id: str):
    """Debug endpoint to inspect investigation state."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    rich_intel = job.get("rich_intel", {})
    relationships = rich_intel.get("relationships", {})
    
    # Count relationship entities
    rel_summary = {}
    for rel_type, entities in relationships.items():
        rel_summary[rel_type] = {
            "count": len(entities) if isinstance(entities, list) else 0,
            "sample": entities[0] if entities else None
        }
    
    return {
        "job_id": job_id,
        "ioc": job.get("ioc"),
        "ioc_type": job.get("ioc_type"),
        "status": job.get("status"),
        "subtasks_count": len(job.get("subtasks", [])),
        "rich_intel_keys": list(rich_intel.keys()),
        "relationships_found": list(relationships.keys()),
        "relationship_summary": rel_summary,
        "graph_node_count_estimate": 1 + len(job.get("subtasks", [])) + sum(len(entities[:5]) for entities in relationships.values() if isinstance(entities, list))
    }

@app.get("/api/investigations/{job_id}/graph")
async def get_investigation_graph(job_id: str):
    """
    Returns graph data (nodes/edges) for visualization.
    Enhanced with debugging and better error handling.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info("graph_request", job_id=job_id)
    
    ioc = job.get("ioc", "Unknown")
    subtasks = job.get("subtasks", [])
    rich_intel = job.get("rich_intel", {})
    
    # Debug logging
    logger.info("graph_data_check", 
                ioc=ioc,
                subtasks_count=len(subtasks),
                rich_intel_keys=list(rich_intel.keys()))
    
    # 1. Central Node (The IOC)
    nodes = [
        {"id": "root", "label": ioc, "color": "#FF4B4B", "size": 30}
    ]
    edges = []
    
    # 2. Subtask Nodes (The Agents)
    for i, task in enumerate(subtasks):
        node_id = f"task_{i}"
        agent_name = task.get("agent", "Unknown")
        
        nodes.append({
            "id": node_id,
            "label": agent_name,
            "color": "#0083B8",
            "size": 20
        })
        
        edges.append({
            "source": "root",
            "target": node_id,
            "label": "assigned_to"
        })
    
    logger.info("graph_subtasks_added", count=len(subtasks))
    
    # 3. Relationship Nodes (From Rich Intel)
    relationships = rich_intel.get("relationships", {})
    logger.info("graph_relationships_check", 
                found=bool(relationships),
                types=list(relationships.keys()) if relationships else [])
    
    if not relationships:
        logger.warning("graph_no_relationships",
                      message="No relationships found in rich_intel. Graph will only show root + subtasks.")
    
    relationship_nodes_added = 0
    
    for rel_type, entities in relationships.items():
        if not entities:
            logger.warning("graph_empty_relationship", rel_type=rel_type)
            continue
        
        logger.info("graph_processing_relationship", 
                   rel_type=rel_type, 
                   entity_count=len(entities))
        
        # Add up to 5 entities per relationship type
        for idx, entity in enumerate(entities[:5]):
            # Validate entity structure
            if not isinstance(entity, dict):
                logger.warning("graph_invalid_entity", 
                              rel_type=rel_type, 
                              entity_type=type(entity).__name__)
                continue
            
            # Entity ID
            ent_id = entity.get("id")
            if not ent_id:
                logger.warning("graph_missing_entity_id", 
                              rel_type=rel_type, 
                              entity_keys=list(entity.keys()))
                continue
            
            # Determine Label
            attrs = entity.get("attributes", {})
            ent_type = entity.get("type", "unknown")
            
            # More robust label extraction
            label = ent_id
            if ent_type == "domain":
                label = attrs.get("host_name") or ent_id
            elif ent_type == "ip_address":
                label = ent_id  # IP is already in the id field
            elif ent_type == "file":
                # Use meaningful_name if available, else truncate hash
                label = attrs.get("meaningful_name") or ent_id[:8] + "..."
            
            # Unique Node ID
            unique_id = f"{rel_type}_{idx}_{ent_id}"
            
            # Determine color by type
            color = "#FFA500"  # Default orange
            if ent_type == "file":
                color = "#FF6B6B"  # Red for files
            elif ent_type == "domain":
                color = "#4ECDC4"  # Teal for domains
            elif ent_type == "ip_address":
                color = "#FFD93D"  # Yellow for IPs
            
            nodes.append({
                "id": unique_id,
                "label": label[:30] + "..." if len(str(label)) > 30 else str(label),
                "color": color,
                "size": 15,
                "title": json.dumps({
                    "type": ent_type,
                    "id": ent_id,
                    **attrs
                }, indent=2)
            })
            
            edges.append({
                "source": "root",
                "target": unique_id,
                "label": rel_type.replace("_", " ")
            })
            
            relationship_nodes_added += 1
    
    logger.info("graph_generation_complete", 
                total_nodes=len(nodes),
                total_edges=len(edges),
                relationship_nodes=relationship_nodes_added)
    
    if relationship_nodes_added == 0:
        logger.warning("graph_no_relationship_nodes",
                      message="No relationship nodes were added. Check if triage agent fetched relationships.")
    
    return {"nodes": nodes, "edges": edges}
