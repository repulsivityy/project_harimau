import os
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

@app.get("/api/investigations/{job_id}/graph")
async def get_investigation_graph(job_id: str):
    """
    Returns graph data (nodes/edges) for visualization.
    MVP: Constructs a simple star graph (IOC -> Subtasks).
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    ioc = job.get("ioc", "Unknown")
    subtasks = job.get("subtasks", [])
    
    # 1. Central Node (The IOC)
    nodes = [
        {"id": "root", "label": ioc, "color": "#FF4B4B", "size": 25} # Red for IOC
    ]
    edges = []
    
    # 2. Subtask Nodes (The Agents)
    for i, task in enumerate(subtasks):
        node_id = f"task_{i}"
        agent_name = task.get("agent", "Unknown")
        
        nodes.append({
            "id": node_id,
            "label": agent_name,
            "color": "#0083B8", # Blue for Agents
            "size": 15
        })
        
        edges.append({
            "source": "root",
            "target": node_id,
            "label": "assigned_to"
        })
        
    return {"nodes": nodes, "edges": edges}
