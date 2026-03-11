import os
import json
import uuid
from datetime import datetime
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
    return {"message": "Harimau Threat Hunter Backend Online"}

# Simple In-Memory Persistence for MVP
JOBS = {}

@app.post("/api/investigate")
async def run_investigation(request: InvestigationRequest):
    """
    Triggers the LangGraph investigation workflow in the background.
    Returns immediately with job_id for polling.
    """
    import asyncio
    
    job_id = str(uuid.uuid4())
    logger.info("investigation_request", job_id=job_id, ioc=request.ioc)
    
    # Initialize Job Status
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "ioc": request.ioc,
        "created_at": "now"
    }
    
    # Run investigation in background
    asyncio.create_task(_run_investigation_background(job_id, request.ioc))
    
    # Return immediately
    return {
        "job_id": job_id,
        "status": "running",
        "message": "Investigation started. Poll /api/investigations/{job_id} for results."
    }

async def _run_investigation_background(job_id: str, ioc: str):
    """Background task that runs the actual investigation with SSE event streaming."""
    from backend.utils.sse_manager import sse_manager
    
    try:
        # Create SSE queue for this investigation
        sse_manager.create_queue(job_id)
        
        # Emit: Investigation started
        await sse_manager.emit_event(job_id, "investigation_started", {
            "job_id": job_id,
            "ioc": ioc,
            "message": "Investigation started"
        })
        
        initial_state = {
            "job_id": job_id,
            "ioc": ioc,
            "messages": [],
            "subtasks": [],
            "specialist_results": {},
            "metadata": {}
        }
        
        # Emit: Workflow execution started
        await sse_manager.emit_event(job_id, "workflow_started", {
            "message": "LangGraph workflow initiated",
            "progress": 5
        })
        
        final_state = await app_graph.ainvoke(initial_state)
        
        # Generate detailed timeline from SSE event history
        timeline_events = sse_manager.get_events(job_id)
        initial_subtasks = []
        
        # Map agent names to specific tasks from triage results
        specialist_results = final_state.get("specialist_results", {})
        specialist_tasks = {}
        for agent_name, agent_data in specialist_results.items():
            if isinstance(agent_data, dict) and agent_data.get("task"):
                specialist_tasks[agent_name] = agent_data.get("task")

        # Track start times to calculate duration
        start_times = {}
        
        # Process events to build timeline
        for event in timeline_events:
            evt_type = event.get("event_type", "")
            data = event.get("data", {})
            timestamp = event.get("timestamp")
            
            if "_started" in evt_type:
                agent = data.get("agent")
                if agent:
                    start_times[agent] = timestamp
            
            elif "_completed" in evt_type:
                agent = data.get("agent")
                if agent:
                    # Calculate duration
                    duration = "N/A"
                    if agent in start_times:
                        try:
                            start_dt = datetime.fromisoformat(start_times[agent])
                            end_dt = datetime.fromisoformat(timestamp)
                            duration = f"{(end_dt - start_dt).total_seconds():.2f}s"
                        except ValueError:
                            pass
                    
                    # Get specific task description if available, else generic message
                    # For Triage/Lead Hunter, use the message. For Specialists, use the assigned task.
                    task_desc = specialist_tasks.get(agent, data.get("message", ""))
                    
                    initial_subtasks.append({
                        "agent": agent,
                        "task": task_desc,
                        "status": "completed",
                        "timestamp": timestamp,
                        "duration": duration
                    })
        
        # Fallback: If no events found (shouldn't happen with SSE), use old method
        if not initial_subtasks:
            logger.warning("sse_no_history_found", job_id=job_id)
            for agent_name, agent_data in specialist_results.items():
                if isinstance(agent_data, dict) and agent_data.get("task"):
                    initial_subtasks.append({
                        "agent": agent_name,
                        "task": agent_data.get("task", ""),
                        "status": "completed",
                        "timestamp": datetime.now().isoformat(),
                        "duration": "N/A"
                    })
        
        # Extract transparency log from SSE event history
        transparency_log = []
        for event in timeline_events:
            event_type = event.get("event_type", "")
            if event_type == "tool_invocation":
                transparency_log.append({
                    "type": "tool",
                    "timestamp": event.get("timestamp"),
                    "agent": event.get("data", {}).get("agent"),
                    "tool": event.get("data", {}).get("tool"),
                    "args": event.get("data", {}).get("args", {})
                })
            elif event_type == "agent_reasoning":
                transparency_log.append({
                    "type": "reasoning",
                    "timestamp": event.get("timestamp"),
                    "agent": event.get("data", {}).get("agent"),
                    "thought": event.get("data", {}).get("thought", "")
                })
        
        # Update Job with results
        result = {
            "job_id": job_id,
            "status": "completed",
            "ioc": final_state.get("ioc") or ioc, 
            "ioc_type": final_state.get("ioc_type"),
            "subtasks": initial_subtasks,  # Use preserved subtasks instead of cleared ones
            "final_report": final_state.get("final_report", "No report generated."),
            "risk_level": final_state.get("metadata", {}).get("risk_level", "Unknown"),
            "gti_score": final_state.get("metadata", {}).get("gti_score", "N/A"),
            "rich_intel": final_state.get("metadata", {}).get("rich_intel", {}),
            "specialist_results": specialist_results,
            "metadata": final_state.get("metadata", {}),
            "investigation_graph": final_state.get("investigation_graph"),  # Add graph to result
            "transparency_log": transparency_log  # Agent transparency events
        }
        JOBS[job_id] = result
        logger.info("investigation_complete", job_id=job_id, status="completed")
        
        # Emit: Investigation completed
        await sse_manager.emit_event(job_id, "investigation_completed", {
            "job_id": job_id,
            "status": "completed",
            "message": "Investigation completed successfully",
            "progress": 100,
            "ioc_type": result.get("ioc_type"),
            "risk_level": result.get("risk_level")
        })
        
    except Exception as e:
        logger.error("investigation_failed", job_id=job_id, error=str(e))
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        
        # Emit: Investigation failed
        await sse_manager.emit_event(job_id, "investigation_failed", {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
            "message": f"Investigation failed: {str(e)}"
        })

@app.get("/api/investigations/{job_id}")
async def get_investigation(job_id: str):
    """
    Get investigation status and results.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/investigations/{job_id}/stream")
async def stream_investigation(job_id: str):
    """
    SSE endpoint for real-time investigation progress streaming.
    
    Streams events as the investigation progresses:
    - investigation_started
    - workflow_started
    - triage_started / triage_completed
    - specialist_started / specialist_completed
    - lead_hunter_started / lead_hunter_completed
    - investigation_completed / investigation_failed
    
    Usage:
        EventSource: new EventSource('/api/investigations/{job_id}/stream')
        Curl: curl -N /api/investigations/{job_id}/stream
    """
    from fastapi.responses import StreamingResponse
    from backend.utils.sse_manager import sse_manager
    
    # Check if job exists
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    logger.info("sse_stream_requested", job_id=job_id)
    
    return StreamingResponse(
        sse_manager.subscribe(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering for Cloud Run
        }
    )

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

'''
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
            
            # Label extraction without truncation for hashes
            label = ent_id
            if ent_type == "domain":
                label = attrs.get("host_name") or ent_id
            elif ent_type == "ip_address":
                label = ent_id  # IP is already in the id field
            elif ent_type == "file":
                # Use meaningful_name if available, else show FULL hash (no truncation)
                label = attrs.get("meaningful_name") or ent_id
            
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
                "label": str(label),  # No truncation - show full hash/domain/IP
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
'''

@app.get("/api/investigations/{job_id}/graph")
async def get_investigation_graph(job_id: str):
    """
    Returns graph data with improved naming conventions for visualization.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")


    from backend.utils.graph_formatter import format_investigation_graph
    return format_investigation_graph(job_id, job)


##########
# added for debugging purposes. to consider removing once prod ready. 
##########
"""
Add this to backend/main.py to diagnose the graph issue.
This endpoint tests each step of the pipeline independently.
"""

@app.get("/api/diagnostic/pipeline/{ioc}")
async def diagnostic_pipeline(ioc: str):
    """
    Tests each step of the investigation pipeline independently.
    Returns detailed diagnostics to identify where the failure occurs.
    """
    from backend.mcp.client import mcp_manager
    import backend.tools.gti as gti
    import re
    
    results = {
        "ioc": ioc,
        "tests": {}
    }
    
    # Test 1: IOC Type Detection
    try:
        ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        if "http" in ioc or "/" in ioc:
            detected_type = "URL"
            rel_tool = "get_entities_related_to_an_url"
            arg = "url"
        elif re.match(ipv4_pattern, ioc):
            detected_type = "IP"
            rel_tool = "get_entities_related_to_an_ip_address"
            arg = "ip_address"
        elif "." in ioc:
            detected_type = "Domain"
            rel_tool = "get_entities_related_to_a_domain"
            arg = "domain"
        else:
            detected_type = "File"
            rel_tool = "get_entities_related_to_a_file"
            arg = "hash"
        
        results["tests"]["ioc_detection"] = {
            "status": "✅ PASS",
            "detected_type": detected_type,
            "rel_tool": rel_tool,
            "arg_name": arg
        }
    except Exception as e:
        results["tests"]["ioc_detection"] = {
            "status": "❌ FAIL",
            "error": str(e)
        }
        return results
    
    # Test 2: Direct GTI API (Python)
    try:
        if detected_type == "IP":
            base_data = await gti.get_ip_report(ioc)
        elif detected_type == "Domain":
            base_data = await gti.get_domain_report(ioc)
        elif detected_type == "File":
            base_data = await gti.get_file_report(ioc)
        else:
            base_data = await gti.get_url_report(ioc)
        
        has_data = bool(base_data and "data" in base_data)
        
        results["tests"]["direct_api"] = {
            "status": "✅ PASS" if has_data else "⚠️ EMPTY",
            "has_data": has_data,
            "keys": list(base_data.keys()) if base_data else [],
            "sample": str(base_data)[:200] if has_data else None
        }
    except Exception as e:
        results["tests"]["direct_api"] = {
            "status": "❌ FAIL",
            "error": str(e)
        }
    
    # Test 3: MCP Connection
    try:
        async with mcp_manager.get_session("gti") as session:
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            
            results["tests"]["mcp_connection"] = {
                "status": "✅ PASS",
                "tools_available": len(tool_names),
                "has_rel_tool": rel_tool in tool_names,
                "sample_tools": tool_names[:5]
            }
    except Exception as e:
        results["tests"]["mcp_connection"] = {
            "status": "❌ FAIL",
            "error": str(e)
        }
        return results
    
    # Test 4: Manual MCP Tool Call (Critical Test)
    try:
        async with mcp_manager.get_session("gti") as session:
            # Try to fetch associations
            res = await session.call_tool(rel_tool, arguments={
                arg: ioc,
                "relationship_name": "associations",
                "descriptors_only": False,
                "limit": 5
            })
            
            tool_output = res.content[0].text if res.content else ""
            
            # Try to parse
            import json
            parsed = None
            entities = []
            try:
                parsed = json.loads(tool_output)
                if isinstance(parsed, dict):
                    entities = parsed.get("data", [])
                elif isinstance(parsed, list):
                    entities = parsed
            except:
                pass
            
            results["tests"]["mcp_tool_call"] = {
                "status": "✅ PASS" if entities else "⚠️ EMPTY",
                "relationship": "associations",
                "raw_output_length": len(tool_output),
                "parsed_successfully": parsed is not None,
                "entities_found": len(entities),
                "sample_output": tool_output[:300]
            }
            
            # Test another relationship based on type
            second_rel = None
            if detected_type == "IP":
                second_rel = "resolutions"
            elif detected_type == "Domain":
                second_rel = "resolutions"
            elif detected_type == "File":
                second_rel = "contacted_ips"
            
            if second_rel:
                res2 = await session.call_tool(rel_tool, arguments={
                    arg: ioc,
                    "relationship_name": second_rel,
                    "descriptors_only": False,
                    "limit": 5
                })
                
                tool_output2 = res2.content[0].text if res2.content else ""
                
                parsed2 = None
                entities2 = []
                try:
                    parsed2 = json.loads(tool_output2)
                    if isinstance(parsed2, dict):
                        entities2 = parsed2.get("data", [])
                    elif isinstance(parsed2, list):
                        entities2 = parsed2
                except:
                    pass
                
                results["tests"]["mcp_second_relationship"] = {
                    "status": "✅ PASS" if entities2 else "⚠️ EMPTY",
                    "relationship": second_rel,
                    "entities_found": len(entities2),
                    "sample_output": tool_output2[:300]
                }
    except Exception as e:
        results["tests"]["mcp_tool_call"] = {
            "status": "❌ FAIL",
            "error": str(e)
        }
    
    # Test 5: Check if Vertex AI is accessible
    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
        
        from langchain_google_vertexai import ChatVertexAI
        llm = ChatVertexAI(
            model="gemini-2.5-flash",
            temperature=0.0,
            project=project_id,
            location=location
        )
        
        # Simple test
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content="Say 'OK'")])
        
        results["tests"]["vertex_ai"] = {
            "status": "✅ PASS",
            "project": project_id,
            "location": location,
            "response": str(response.content)[:100]
        }
    except Exception as e:
        results["tests"]["vertex_ai"] = {
            "status": "❌ FAIL",
            "error": str(e)
        }
    
    # Summary
    all_passed = all(
        test.get("status", "").startswith("✅") 
        for test in results["tests"].values()
    )
    
    results["summary"] = {
        "all_tests_passed": all_passed,
        "diagnosis": ""
    }
    
    # Provide diagnosis
    if not results["tests"]["mcp_connection"].get("status", "").startswith("✅"):
        results["summary"]["diagnosis"] = "MCP connection is failing. Check VT_APIKEY environment variable."
    elif results["tests"]["mcp_tool_call"].get("entities_found", 0) == 0:
        results["summary"]["diagnosis"] = f"MCP tools work, but '{ioc}' has NO relationships in VirusTotal database. Try a different IOC (known malicious hash/IP)."
    elif not results["tests"]["vertex_ai"].get("status", "").startswith("✅"):
        results["summary"]["diagnosis"] = "Vertex AI connection failing. Check GOOGLE_CLOUD_PROJECT and IAM permissions."
    else:
        results["summary"]["diagnosis"] = "All components working. Issue is in agent logic. Check logs for 'triage_agent_invoking_tool'."
    
    return results


@app.get("/api/diagnostic/test-iocs")
async def get_test_iocs():
    """
    Returns known malicious IOCs that should have relationships.
    Use these for testing instead of 1.1.1.1
    """
    return {
        "message": "Use these IOCs for testing - they have known relationships",
        "test_iocs": {
            "malicious_ip": "185.220.101.188",  # associated with apt44
            "malicious_domain": "ggovua.link",  # associated with apt44
            "malicious_file": "bf458e6b57431f1038e547ab69f28d03e4a33991caaca738997647a450f99a8b",  # associated with apt44
            "note": "these are associated with APT44."
        }
    }

@app.get("/api/diagnostic/tool-test/{ioc}")
async def test_tool_directly(ioc: str):
    """Test MCP tool and show actual response structure"""
    from backend.mcp.client import mcp_manager
    
    try:
        async with mcp_manager.get_session("gti") as session:
            import re
            # Only support IP and File for this quick valid test
            ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
            if re.match(ipv4_pattern, ioc):
                tool_name = "get_entities_related_to_an_ip_address"
                arg_name = "ip_address"
                rel_name = "resolutions"
            else:
                 tool_name = "get_entities_related_to_a_file"
                 arg_name = "hash"
                 rel_name = "contacted_domains"

            res = await session.call_tool(
                tool_name,
                arguments={
                    arg_name: ioc,
                    "relationship_name": rel_name,
                    "descriptors_only": False,
                    "limit": 5
                }
            )
            
            raw_output = res.content[0].text if res.content else ""
            
            # Try to parse
            import json
            parsed = json.loads(raw_output)
            
            return {
                "raw_length": len(raw_output),
                "raw_sample": raw_output[:500],
                "parsed_type": type(parsed).__name__,
                "parsed_keys": list(parsed.keys()) if isinstance(parsed, dict) else None,
                "parsed_sample": parsed if len(str(parsed)) < 1000 else str(parsed)[:1000]
            }
    except Exception as e:
        return {"error": str(e)}

# ============================================
# SSE Compatibility Test Endpoint
# ============================================

@app.get("/api/test/sse")
async def test_sse_compatibility():
    """
    Test endpoint to validate SSE works on Cloud Run.
    
    This endpoint:
    1. Streams 10 events over 60 seconds (6 seconds apart)
    2. Includes keepalive pings every 3 seconds
    3. Uses proper headers to prevent buffering
    
    Test with:
        curl -N https://your-backend-url/api/test/sse
    
    Expected behavior:
    - Events should appear every 6 seconds in real-time
    - If events arrive in a burst at the end, Cloud Run is buffering (problem)
    - If events stream smoothly, SSE is compatible (success)
    """
    import asyncio
    import time
    from datetime import datetime
    from fastapi.responses import StreamingResponse
    
    async def event_generator():
        """Generate test events with keepalive pings."""
        logger.info("sse_test_started", message="Client connected to SSE test endpoint")
        
        try:
            for i in range(10):
                # Send numbered event
                timestamp = datetime.now().isoformat()
                event_data = {
                    "event_number": i + 1,
                    "timestamp": timestamp,
                    "message": f"Test event {i + 1}/10"
                }
                
                event_payload = f"data: {json.dumps(event_data)}\n\n"
                logger.info("sse_test_event", event_number=i + 1)
                yield event_payload
                
                # Wait 6 seconds, but send keepalive pings every 3 seconds
                for _ in range(2):
                    await asyncio.sleep(3)
                    # Send keepalive comment (ignored by EventSource clients)
                    yield ": keepalive\n\n"
            
            # Send completion event
            completion_data = {
                "event_number": "final",
                "timestamp": datetime.now().isoformat(),
                "message": "Test completed successfully",
                "status": "complete"
            }
            yield f"data: {json.dumps(completion_data)}\n\n"
            logger.info("sse_test_completed", message="All events sent successfully")
            
        except asyncio.CancelledError:
            logger.info("sse_test_cancelled", message="Client disconnected")
            raise
        except Exception as e:
            logger.error("sse_test_error", error=str(e))
            error_data = {"error": str(e), "status": "failed"}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx/proxy buffering
        }
    )