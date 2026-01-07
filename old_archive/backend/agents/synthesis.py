"""
Synthesis Agent - Report Generation
"""

from datetime import datetime

def create_synthesis_agent(logger):
    """
    Factory function for synthesis agent.
    
    Args:
        logger: InvestigationLogger instance
    
    Returns:
        Async agent function
    """
    
    async def synthesis_agent(state: dict):
        """
        Synthesis Agent - Generate final report.
        
        Process:
        1. Aggregate findings
        2. Generate Markdown report
        3. Update state
        """
        logger.log("INFO", "synthesis", "Generating final report")
        
        ioc = state["ioc"]
        ioc_type = state["ioc_type"]
        verdict = state.get("verdict", "UNKNOWN")
        score = 0
        
        # Find Triage Score
        for findings in state.get("findings", []):
            if findings["agent"] == "triage":
                score = findings.get("score", 0)
                break
        
        # Generate Markdown Report
        report = f"""# Investigation Report: {ioc}

**Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Verdict**: {verdict}
**Score**: {score}/100
**Type**: {ioc_type}

## Executive Summary
The IOC `{ioc}` has been analyzed and classified as **{verdict}** with a threat score of **{score}**.

## Key Findings
"""

        for finding in state.get("findings", []):
            agent = finding["agent"].title()
            d = finding.get("decision", "No decision")
            v = finding.get("verdict", "UNKNOWN")
            report += f"- **{agent}**: {v} - {d}\n"
            
        report += "\n## Recommendations\n"
        if verdict == "MALICIOUS":
            report += "- Block this IOC immediately.\n- Investigate internal logs for contact.\n"
        elif verdict == "SUSPICIOUS":
            report += "- Monitor traffic associated with this IOC.\n"
        else:
            report += "- No immediate action required.\n"

        state["report"] = report
        state["status"] = "complete"  # Ensure complete
        
        logger.log("INFO", "synthesis", "Report generated successfully")
        state["agents_run"].append("synthesis")
        
        return state

    return synthesis_agent
