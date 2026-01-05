"""
Triage Agent - IOC Classification and Initial Assessment
"""

import re
from backend.tools.mcp_registry import mcp_registry
from backend.utils.ioc_utils import classify_ioc_type
from backend.utils.gti_parser import parse_gti_response


def create_triage_agent(logger):
    """
    Factory function for triage agent.
    
    Args:
        logger: InvestigationLogger instance
    
    Returns:
        Async agent function
    """
    
    async def triage_agent(state: dict):
        """
        Triage Agent - Initial IOC assessment.
        
        Process:
        1. Classify IOC type
        2. Query GTI for threat intelligence
        3. Extract verdict and score
        4. Add root node to graph
        5. Make routing decision
        """
        
        logger.log("INFO", "triage", "Starting IOC classification")
        
        ioc = state["ioc"]
        
        # Step 1: Classify IOC type
        ioc_type = classify_ioc_type(ioc)
        state["ioc_type"] = ioc_type
        
        logger.log("INFO", "triage", f"Classified IOC as: {ioc_type}")
        
        # Step 2: Query GTI for threat intelligence
        logger.log("INFO", "triage", "Querying GTI for threat intelligence")
        
        # Map IOC Type to Specific MCP Tool
        tool_mapping = {
            "file": ("get_file_report", "hash"),
            "ip": ("get_ip_address_report", "ip_address"),
            "domain": ("get_domain_report", "domain"),
            "url": ("get_url_report", "url")
        }
        
        if ioc_type not in tool_mapping:
             logger.log("WARN", "triage", f"Unsupported IOC type for GTI: {ioc_type}")
             # Treat as unknown/skip
             state["verdict"] = "UNKNOWN"
             return state

        tool_name, arg_name = tool_mapping[ioc_type]

        try:
            gti_result = await mcp_registry.call(
                server="gti",
                tool=tool_name,
                args={arg_name: ioc}
            )
            
            # Parse Raw Result
            parsed = parse_gti_response(gti_result)
            
            # Log API call
            logger.log_api_call(
                tool=tool_name,
                request={arg_name: ioc},
                response=parsed, # Log parsed for readability, or gti_result for raw? Let's log parsed summary.
                duration=gti_result.get("_duration", 0)
            )
            
        except Exception as e:
            logger.log("ERROR", "triage", f"GTI lookup failed: {e}")
            
            # Create error node
            state["graph_nodes"].append({
                "id": ioc,
                "type": ioc_type,
                "verdict": "ERROR",
                "score": 0,
                "error": str(e),
                "analyzed": False
            })
            
            state["status"] = "failed"
            return state
        
        # Step 3: Extract verdict and score
        verdict = parsed.get("verdict", "UNKNOWN")
        score = parsed.get("score", 0)
        malicious_votes = parsed.get("malicious_votes", 0)
        total_votes = parsed.get("total_votes", 0)
        
        logger.log(
            "INFO",
            "triage",
            f"GTI verdict: {verdict} (score: {score}, detections: {malicious_votes}/{total_votes})"
        )
        
        # Store verdict in state for routing
        state["verdict"] = verdict
        
        # Step 4: Add root node to graph
        state["graph_nodes"].append({
            "id": ioc,
            "type": ioc_type,
            "verdict": verdict,
            "score": score,
            "malicious_votes": malicious_votes,
            "total_votes": total_votes,
            "analyzed": False,  # Will be analyzed by specialist
            "data": gti_result
        })
        
        # Update budget
        state["budget"].api_calls_made += 1
        state["budget"].nodes_created += 1
        
        # Step 5: Make routing decision
        if verdict in ["MALICIOUS", "SUSPICIOUS"]:
            if ioc_type == "file":
                decision = "Route to Malware Hunter"
            else:
                decision = "Route to Infrastructure Hunter"
        else:
            decision = "Skip to Synthesis (benign IOC)"
        
        logger.log_decision(
            agent="triage",
            decision=decision,
            reasoning=f"Verdict: {verdict}, Type: {ioc_type}, Score: {score}"
        )
        
        # Track agent execution
        state["agents_run"].append("triage")
        state["findings"].append({
            "agent": "triage",
            "verdict": verdict,
            "score": score,
            "decision": decision
        })
        
        return state
    
    return triage_agent
