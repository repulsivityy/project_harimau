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

@app.post("/investigate")
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
    
    try:
        # Run the Graph
        # Note: ainvoke returns the final state
        final_state = await app_graph.ainvoke(initial_state)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "ioc_type": final_state.get("ioc_type"),
            "subtasks": final_state.get("subtasks"),
            # In MVP, this comes from Triage Agent directly logging to state
        }
        
    except Exception as e:
        logger.error("investigation_failed", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
