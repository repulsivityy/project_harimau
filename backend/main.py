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
            "ioc": final_state.get("ioc") or request.ioc,  # ✅ ADD THIS LINE
            "ioc_type": final_state.get("ioc_type"),
            "subtasks": final_state.get("subtasks"),
            "final_report": final_state.get("final_report", "No report generated."),
            "risk_level": final_state.get("metadata", {}).get("risk_level", "Unknown"),
            "gti_score": final_state.get("metadata", {}).get("gti_score", "N/A"),
            "rich_intel": final_state.get("metadata", {}).get("rich_intel", {}),
            "metadata": final_state.get("metadata", {}),  # ✅ Added full metadata for frontend transparency
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
'''
# Improved Graph Endpoint with Better Naming
# Replace the get_investigation_graph function in backend/main.py

@app.get("/api/investigations/{job_id}/graph")
async def get_investigation_graph(job_id: str):
    """
    Returns graph data with improved naming conventions for visualization.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info("graph_request", job_id=job_id)
    
    ioc = job.get("ioc", "Unknown")
    ioc_type = job.get("ioc_type", "Unknown")
    subtasks = job.get("subtasks", [])
    rich_intel = job.get("rich_intel", {})
    
    # 1. Central Node (The IOC) with better label
    root_label = ioc
    if ioc_type == "File":
        root_label = f"File: {ioc[:16]}..." if len(ioc) > 16 else f"File: {ioc}"
    elif ioc_type == "IP":
        root_label = f"IP: {ioc}"
    elif ioc_type == "Domain":
        root_label = f"Domain: {ioc}"
    elif ioc_type == "URL":
        # Extract domain from URL
        root_label = f"URL: {ioc[:30]}..."
    
    nodes = [
        {
            "id": "root", 
            "label": root_label, 
            "color": "#FF4B4B",  # Red for IOC
            "size": 35,
            "title": f"IOC: {ioc}\nType: {ioc_type}"
        }
    ]
    edges = []
    
    # Note: Agent subtasks are NOT added to graph - only IOC relationships
    logger.info("graph_config", agent_nodes_disabled=True, reason="only_show_ioc_relationships")
    
    # 3. Relationship Nodes with Visual Enhancements
    relationships = rich_intel.get("relationships", {})
    
    # Exclude non-graph relationships
    EXCLUDE_RELATIONSHIPS = ["attack_techniques", "malware_families", "associations", "campaigns", "related_threat_actors"]
    filtered_relationships = {
        k: v for k, v in relationships.items() 
        if k not in EXCLUDE_RELATIONSHIPS and v
    }
    
    logger.info("graph_building", 
                total_rels=len(relationships),
                showing_rels=len(filtered_relationships))

    # Helper: Entity Labeler
    def get_entity_label(entity: dict) -> str:
        ent_type = entity.get("type", "unknown")
        ent_id = entity.get("id", "unknown")
        attrs = entity.get("attributes", {})
        

        
        if ent_type == "url":
            # 1. Try attributes.last_final_url (Best)
            if attrs.get("last_final_url"):
                return attrs.get("last_final_url")

            # 2. Try attributes.url
            if attrs.get("url"):
                return attrs.get("url")
            
            # 3. Try context_attributes (Backup)
            context_attrs = entity.get("context_attributes", {})
            if context_attrs.get("url"):
                return context_attrs.get("url")
            
            # 4. Fallback: Full ID (Hash)
            # Remove base64 decoding as attributes should be populated
            return ent_id
            
            # 4. Fallback: Full ID (Hash)
            return ent_id
            
        elif ent_type == "file":
            # Format: Full SHA256\n(truncated_filename.ext)
            
            # 1. meaningful_name
            name = attrs.get("meaningful_name")
            
            # 2. names list (take first)
            if not name and attrs.get("names"):
                name = attrs.get("names")[0]
                
            if name:
                # Smart truncation: Keep first 24 chars + extension
                import os
                base, ext = os.path.splitext(name)
                if len(base) > 24:
                    # Truncate to 24 chars, keep extension
                    truncated = base[:24] + "..." + ext
                else:
                    truncated = name
                return f"{ent_id}\n({truncated})"  # Full hash + truncated filename
            
            return ent_id  # Full hash if no filename
            
        elif ent_type == "domain":
            return attrs.get("host_name", ent_id)
            
        elif ent_type == "ip_address":
            return ent_id
            
        return ent_id  # Default: show full ID

    # Process Relationships with Clustering
    node_registry = set(["root"]) # Track existing nodes to prevent dups
    
    for rel_type, entities in filtered_relationships.items():
        logger.info("graph_processing_relationship", 
                   rel_type=rel_type, 
                   entity_count=len(entities))
        
        # Clustering Logic: If multiple entities, create a group node
        use_clustering = len(entities) > 1
        source_id = "root"
        
        if use_clustering:
            group_id = f"group_{rel_type}"
            group_label = rel_type.replace("_", " ").title()
            
            nodes.append({
                "id": group_id,
                "label": group_label,
                "color": "#2C3E50",  # Dark BlueGrey (Matches 'Black' in Legend)
                "size": 25,  # Larger than entities, smaller than root
                "shape": "box",  # Box shape for groups
                "title": f"{group_label}\n{len(entities)} entities"
            })
            
            edges.append({
                "source": "root",
                "target": group_id,
                "label": "",  # No label on this edge (label is on the group node)
            })
            
            source_id = group_id
            
        # Add entities (limit to 15 to prevent graph overload)
        display_entities = entities[:15]
        
        for idx, entity in enumerate(display_entities):
            ent_id = entity.get("id")
            if not ent_id: continue
            
            unique_id = f"{rel_type}_{ent_id}"
            
            # Skip if already added
            if unique_id in node_registry: continue
            node_registry.add(unique_id)
            
            ent_type = entity.get("type", "unknown")
            
            # Color Palette
            color_map = {
                "file": "#9B59B6",           # Purple
                "domain": "#E67E22",         # Orange
                "ip_address": "#E67E22",     # Orange
                "url": "#2ECC71",            # Green (Matches Legend)
                "collection": "#3498DB",     # Blue
            }
            color = color_map.get(ent_type, "#95A5A6") # Grey default
            
            nodes.append({
                "id": unique_id,
                "label": get_entity_label(entity),
                "color": color,
                "size": 20, # Standard entity size
                "title": json.dumps(entity.get("attributes", {}), indent=2)
            })
            
            edges.append({
                "source": source_id,  # Either root or group
                "target": unique_id,
                "label": "" if use_clustering else rel_type.replace("_", " ")
            })
        
        # If truncated, add "+X more" indicator node
        if len(entities) > 15:
            remaining = len(entities) - 15
            overflow_id = f"overflow_{rel_type}"
            
            nodes.append({
                "id": overflow_id,
                "label": f"+{remaining} more",
                "color": "#BDC3C7",  # Light grey
                "size": 15,
                "shape": "box",
                "title": f"{remaining} additional {rel_type} entities not shown"
            })
            
            edges.append({
                "source": source_id,
                "target": overflow_id,
                "label": "",
                "dashes": True
            })


    return {"nodes": nodes, "edges": edges}


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