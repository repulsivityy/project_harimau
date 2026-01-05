import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header
from datetime import datetime
from pydantic import BaseModel
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

from backend.models import InvestigationState
from backend.database import init_db, JobManager, get_db_pool
from backend.tools.mcp_registry import mcp_registry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Harimau Threat Hunter (Async)")

class InvestigationRequest(BaseModel):
    ioc: str
    ioc_type: Optional[str] = "unknown"

class InvestigationResponse(BaseModel):
    job_id: str
    status: str
    message: str

@app.on_event("startup")
async def startup_event():
    """Initialize DB and MCP"""
    try:
        # 1. Initialize Database
        db_url = os.getenv("DB_URL")
        if not db_url:
            logger.error("DB_URL not configured - cannot start asynchronously")
            raise ValueError("DB_URL environment variable is required") 
        else:
            await init_db()
            logger.info("Database initialized successfully")

        # 2. Initialize MCP (if needed for SSE)
        if os.getenv("GTI_MCP_MODE") == "http":
            logger.info("Configured for HTTP MCP connection")
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise e

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "0.2.0-async"}

@app.post("/investigate", response_model=InvestigationResponse)
async def start_investigation(request: InvestigationRequest):
    """
    Start an asynchronous investigation.
    1. Create Job in DB
    2. Enqueue Cloud Task
    """
    if not request.ioc:
        raise HTTPException(status_code=400, detail="IOC is required")
        
    try:
        # 1. Create Job
        job_id = await JobManager.create_job(request.ioc, status=JobStatus.QUEUED.value)
        
        # 2. Enqueue Task (Cloud Tasks)
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        queue = os.getenv("CLOUD_TASKS_QUEUE", "investigation-queue")
        location = os.getenv("CLOUD_TASKS_LOCATION", "asia-southeast1")
        # Service URL for Cloud Tasks callback
        service_url = os.getenv("SERVICE_URL")
        if not service_url:
            logger.error("SERVICE_URL env var is required for Cloud Tasks")
            raise HTTPException(status_code=500, detail="Configuration Error: SERVICE_URL missing")
        
        # If running locally without service_url, we can't really enqueue to ourselves easily unless using ngrok
        # For Cloud Run, SERVICE_URL should be set or derived
        
        # Validate
        logger.info(f"Enqueue Config - Project: {project}, Queue: {queue}, ServiceURL: {service_url}")
        
        if project and service_url:
            # We trust SERVICE_URL since it's validated above.
            client = tasks_v2.CloudTasksClient()
            parent = client.queue_path(project, location, queue)
            
            task = {
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": f"{service_url}/internal/worker",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"job_id": job_id, "ioc": request.ioc}).encode(),
                    "oidc_token": {"service_account_email": os.getenv("SERVICE_ACCOUNT_EMAIL")}
                }
            }
            
            response = client.create_task(request={"parent": parent, "task": task})
            logger.info(f"Task created: {response.name}")
        else:
            error_msg = f"Cloud Tasks configuration missing (Project={project}, ServiceURL={service_url}). Cannot enqueue job."
            logger.error(error_msg)
            # Fail the job immediately so it doesn't stick in QUEUED
            await JobManager.update_job(job_id, JobStatus.FAILED.value, {"error": error_msg})
            raise HTTPException(status_code=500, detail=error_msg)
            
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Investigation started"
        }
            
    except Exception as e:
        logger.error(f"Failed to start investigation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/investigations/{job_id}")
async def get_investigation_status(job_id: str):
    """Poll investigation status"""
    job = await JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/internal/worker")
async def investigation_worker(
    request: Request,
    x_cloudtasks_queuename: Optional[str] = Header(None)
):
    """
    Worker endpoint processed by Cloud Tasks.
    Protected by checking X-CloudTasks-QueueName header.
    """
    # Security Check
    if not x_cloudtasks_queuename and os.getenv("ENV") != "dev":
        logger.warning("Unauthorized worker access attempt (Example - enforced in prod)")
        raise HTTPException(status_code=403, detail="Access Forbidden")
    
    payload = await request.json()
    job_id = payload.get("job_id")
    ioc = payload.get("ioc")
    
    await run_worker_logic(job_id, ioc)
    return {"status": "success"}

async def run_worker_logic(job_id: str, ioc: str):
    if not job_id or not ioc:
        logger.error("Invalid worker payload")
        return
        
    logger.info(f"Worker processing job {job_id} for IOC {ioc}")
    
    try:
        # Update Status -> Running
        await JobManager.update_job(job_id, JobStatus.RUNNING.value)
        
        # Initialize Investigation Logger
        from backend.logging_config import InvestigationLogger
        inv_logger = InvestigationLogger(job_id, debug_mode=False) # Enable debug via env var if needed
        
        # Initial State
        state = {
            "ioc": ioc,
            "ioc_type": "unknown",
            "graph_nodes": [],
            "graph_edges": [],
            "iteration": 0,
            "max_iterations": 3,
            "agents_run": [],
            "status": "running",
            "budget": {
                "max_api_calls": 200,
                "max_graph_nodes": 50,
                "max_wall_time": 600,
                "api_calls_made": 0,
                "nodes_created": 0,
                "start_time": time.time()
            },
            "findings": [],
            "report": ""
        }
        
        # Run Workflow
        # Initialize Checkpointer
        # Initialize Checkpointer
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from urllib.parse import urlparse, parse_qs, unquote
        
        db_url = os.getenv("DB_URL")
        
        # Convert SQLAlchemy URL to DSN for psycopg
        # Format: postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/instance
        parsed = urlparse(db_url)
        query = parse_qs(parsed.query)
        host_socket = query.get("host", [None])[0]
        
        dsn_parts = []
        if parsed.path:
            dsn_parts.append(f"dbname={parsed.path.lstrip('/')}")
        if parsed.username:
            dsn_parts.append(f"user={parsed.username}")
        if parsed.password:
            dsn_parts.append(f"password={parsed.password}")
        if host_socket:
            dsn_parts.append(f"host={host_socket}")
        elif parsed.hostname:
             dsn_parts.append(f"host={parsed.hostname}")
             
        dsn = " ".join(dsn_parts)
        
        async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
            # Ensure tables exist (idempotent)
            await checkpointer.setup()
            
            # Pass custom logger and checkpointer
            app_workflow = create_workflow(logger=inv_logger, checkpointer=checkpointer)
            
            # Configure thread_id for persistence (using job_id)
            config = {"configurable": {"thread_id": job_id}}
            
            final_state = await app_workflow.ainvoke(state, config=config)
        
        # Serialize Result
        result = {
            "status": final_state.get("status"),
            "verdict": final_state.get("verdict"),
            "findings": final_state.get("findings", []),
            "report": final_state.get("report"),
            "graph_size": len(final_state.get("graph_nodes", []))
        }
        
        # Update Job -> Complete
        await JobManager.update_job(job_id, JobStatus.COMPLETED.value, result)
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        try:
            await JobManager.update_job(job_id, JobStatus.FAILED.value, {"error": str(e)})
        except Exception as db_error:
            logger.critical(f"Failed to submit failure status for job {job_id}: {db_error}")
