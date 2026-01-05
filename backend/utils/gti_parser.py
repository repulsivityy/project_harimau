"""
GTI (VirusTotal) Response Parser
Adapts logic from legacy gti_mcp_tool.py
"""

from typing import Dict, Any, Optional

def parse_gti_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse raw GTI/VirusTotal API response into a simplified structure.
    
    Args:
        data: Raw JSON response from MCP tool
        
    Returns:
        Dict containing:
        - verdict: MALICIOUS, SUSPICIOUS, BENIGN, UNKNOWN
        - score: Threat score (0-100)
        - malicious_votes: Number of malicious detections
        - total_votes: Total number of scanners
        - attributes: Raw attributes for deeper analysis
    """
    
    # Handle wrapping
    if "data" in data:
        data = data["data"]
        
    attrs = data.get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    
    # Extract counts
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    total = sum(stats.values()) if stats else 0
    
    # Extract GTI specific assessment
    gti_assessment = attrs.get("gti_assessment", {})
    gti_verdict = gti_assessment.get("verdict", {}).get("value")
    gti_score = gti_assessment.get("threat_score", {}).get("value", 0)
    
    # Determine Unified Verdict
    if gti_verdict:
        verdict = gti_verdict.upper()
    elif malicious > 0:
        verdict = "MALICIOUS"
    elif suspicious > 0:
        verdict = "SUSPICIOUS"
    else:
        verdict = "BENIGN"
        
    # Fallback score if not from GTI
    if not gti_score:
        if malicious > 5: gti_score = 90
        elif malicious > 0: gti_score = 70
        elif suspicious > 0: gti_score = 40
        else: gti_score = 0
            
    return {
        "verdict": verdict,
        "score": gti_score,
        "malicious_votes": malicious,
        "total_votes": total,
        "raw_attributes": attrs
    }
