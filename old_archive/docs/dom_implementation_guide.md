# Implementation Guide - Threat Hunter Platform

**Version:** 1.0  
**Date:** January 2025  
**Purpose:** Complete pseudocode reference for Phase 1 implementation  
**Audience:** Developers and AI coding assistants

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Components](#2-core-components)
   - 2.1 [CLI Entry Point](#21-cli-entry-point)
   - 2.2 [LangGraph Workflow](#22-langgraph-workflow)
   - 2.3 [Agents](#23-agents)
   - 2.4 [Supporting Infrastructure](#24-supporting-infrastructure)
3. [Helper Functions](#3-helper-functions)
4. [Implementation Checklist](#4-implementation-checklist)

---

## 1. Overview

This guide provides complete pseudocode for all components of the Threat Hunter Platform Phase 1 (Backend CLI).

**Implementation Order:**
1. Week 1: Core infrastructure (logging, MCP registry, graph utilities)
2. Week 1-2: Agents (triage, malware, infrastructure, synthesis)
3. Week 2: LangGraph workflow integration
4. Week 3: CLI interface and benchmarking

**Key Principles:**
- All code is evidence-based (no hallucinations)
- Comprehensive logging at every decision point
- Budget checks before expensive operations
- Graceful degradation on errors

---

## 2. Core Components

### 2.1 CLI Entry Point

**File:** `backend/cli.py`

**Purpose:** Command-line interface for running investigations
```python
#!/usr/bin/env python3
"""
CLI Entry Point for Threat Hunter Platform
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Import core components
from backend.logging_config import InvestigationLogger
from backend.graph_workflow import create_investigation_workflow
from backend.models import InvestigationState, InvestigationBudget
from langgraph.checkpoint.memory import MemorySaver


def generate_investigation_id() -> str:
    """Generate unique investigation ID"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"inv-{timestamp}"


async def run_investigation(ioc: str, debug: bool = False) -> dict:
    """
    Run a complete investigation for a given IOC.
    
    Args:
        ioc: The IOC to investigate (hash, IP, domain, URL)
        debug: Enable debug mode logging
    
    Returns:
        Investigation results including report and graph
    """
    # Generate investigation ID
    investigation_id = generate_investigation_id()
    
    # Initialize logger
    logger = InvestigationLogger(investigation_id, debug_mode=debug)
    logger.log("INFO", "system", f"Starting investigation: {ioc}")
    
    # Create LangGraph workflow
    workflow = create_investigation_workflow(logger)
    app = workflow.compile(checkpointer=MemorySaver())
    
    # Initial state
    initial_state = {
        "ioc": ioc,
        "ioc_type": "",
        "graph_nodes": [],
        "graph_edges": [],
        "iteration": 0,
        "max_iterations": 3,
        "agents_run": [],
        "findings": [],
        "status": "running",
        "budget": InvestigationBudget(),
        "report": ""
    }
    
    # Execute workflow
    try:
        logger.log("INFO", "system", "Executing LangGraph workflow")
        
        result = await app.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": investigation_id}}
        )
        
        logger.log("INFO", "system", "Investigation complete")
        
        # Save outputs
        save_report(investigation_id, result["report"])
        save_graph(investigation_id, result["graph_nodes"], result["graph_edges"])
        
        return {
            "investigation_id": investigation_id,
            "status": "complete",
            "ioc": ioc,
            "report": result["report"],
            "graph": {
                "nodes": result["graph_nodes"],
                "edges": result["graph_edges"]
            }
        }
        
    except Exception as e:
        logger.log("ERROR", "system", f"Investigation failed: {e}")
        raise


def save_report(investigation_id: str, report_content: str):
    """Save Markdown report to file"""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    report_file = reports_dir / f"{investigation_id}_report.md"
    report_file.write_text(report_content)
    
    print(f"📄 Report saved: {report_file}")


def save_graph(investigation_id: str, nodes: list, edges: list):
    """Save graph as JSON"""
    import json
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    graph_file = reports_dir / f"{investigation_id}_graph.json"
    
    graph_data = {
        "investigation_id": investigation_id,
        "nodes": nodes,
        "edges": edges
    }
    
    graph_file.write_text(json.dumps(graph_data, indent=2, default=str))
    
    print(f"🕸️  Graph saved: {graph_file}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Threat Hunter Platform - AI-Powered IOC Investigation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Commands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Investigate command
    investigate_parser = subparsers.add_parser(
        'investigate',
        help='Run investigation for a single IOC'
    )
    investigate_parser.add_argument(
        'ioc',
        help='IOC to investigate (hash, IP, domain, URL)'
    )
    investigate_parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose logging)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'investigate':
        print(f"\n{'='*60}")
        print("🔍 AI THREAT HUNTER")
        print(f"{'='*60}")
        print(f"IOC: {args.ioc}")
        print(f"Debug Mode: {'ENABLED' if args.debug else 'DISABLED'}")
        print(f"{'='*60}\n")
        
        try:
            result = asyncio.run(run_investigation(args.ioc, args.debug))
            
            print(f"\n{'='*60}")
            print("✅ INVESTIGATION COMPLETE")
            print(f"{'='*60}")
            print(f"Investigation ID: {result['investigation_id']}")
            print(f"Status: {result['status']}")
            print(f"Report: reports/{result['investigation_id']}_report.md")
            print(f"Graph: reports/{result['investigation_id']}_graph.json")
            
            if args.debug:
                print(f"\nDebug logs: logs/debug/investigation_{result['investigation_id']}.log")
            
        except KeyboardInterrupt:
            print("\n⚠️  Investigation interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Investigation failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
```

---

### 2.2 LangGraph Workflow

**File:** `backend/graph_workflow.py`

**Purpose:** LangGraph state machine for investigation orchestration
```python
"""
LangGraph Workflow for Investigation Orchestration
"""

from langgraph.graph import StateGraph, END
from backend.models import InvestigationState
from backend.agents.triage import create_triage_agent
from backend.agents.malware import create_malware_agent
from backend.agents.infrastructure import create_infrastructure_agent
from backend.agents.synthesis import create_synthesis_agent


def create_investigation_workflow(logger):
    """
    Create the LangGraph state machine for investigations.
    
    Args:
        logger: InvestigationLogger instance
    
    Returns:
        Compiled LangGraph workflow
    """
    
    # Create state graph
    workflow = StateGraph(InvestigationState)
    
    # Add agents as nodes
    workflow.add_node("triage", create_triage_agent(logger))
    workflow.add_node("malware", create_malware_agent(logger))
    workflow.add_node("infrastructure", create_infrastructure_agent(logger))
    workflow.add_node("synthesis", create_synthesis_agent(logger))
    
    # Set entry point
    workflow.set_entry_point("triage")
    
    # Routing after triage
    def route_after_triage(state: InvestigationState) -> str:
        """Decide where to go after triage based on IOC type and verdict"""
        
        ioc_type = state["ioc_type"]
        verdict = state.get("verdict", "UNKNOWN")
        
        # If benign, skip to synthesis
        if verdict == "BENIGN":
            logger.log("INFO", "router", "IOC is benign, skipping to synthesis")
            return "synthesis"
        
        # Route based on IOC type
        if ioc_type == "file":
            logger.log("INFO", "router", "Routing to malware agent (file IOC)")
            return "malware"
        elif ioc_type in ["ip", "domain", "url"]:
            logger.log("INFO", "router", "Routing to infrastructure agent (network IOC)")
            return "infrastructure"
        else:
            logger.log("WARN", "router", f"Unknown IOC type: {ioc_type}, defaulting to synthesis")
            return "synthesis"
    
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "malware": "malware",
            "infrastructure": "infrastructure",
            "synthesis": "synthesis"
        }
    )
    
    # Check if more work needed after specialist agents
    def check_investigation_complete(state: InvestigationState) -> str:
        """
        Decide if investigation should continue or proceed to synthesis.
        
        Logic:
        1. Check budget - if exhausted, go to synthesis
        2. Check iterations - if max reached, go to synthesis
        3. Find unanalyzed nodes:
           - If unanalyzed files exist → route to malware
           - Else if unanalyzed network IOCs exist → route to infrastructure
           - Else → synthesis (investigation complete)
        """
        
        # Check budget
        budget = state["budget"]
        can_continue, reason = budget.can_continue()
        
        if not can_continue:
            logger.log("WARN", "router", f"Budget exhausted: {reason}")
            return "synthesis"
        
        # Check iterations
        if state["iteration"] >= state["max_iterations"]:
            logger.log("INFO", "router", f"Max iterations reached ({state['max_iterations']})")
            return "synthesis"
        
        # Find unanalyzed nodes
        unanalyzed = find_unanalyzed_nodes(state["graph_nodes"])
        
        if unanalyzed["files"]:
            logger.log(
                "INFO",
                "router",
                f"Found {len(unanalyzed['files'])} unanalyzed files, routing to malware agent"
            )
            state["iteration"] += 1
            return "malware"
        
        elif unanalyzed["network"]:
            logger.log(
                "INFO",
                "router",
                f"Found {len(unanalyzed['network'])} unanalyzed network IOCs, routing to infrastructure agent"
            )
            state["iteration"] += 1
            return "infrastructure"
        
        else:
            logger.log("INFO", "router", "No unanalyzed nodes, investigation complete")
            return "synthesis"
    
    # Add conditional edges after specialist agents
    workflow.add_conditional_edges(
        "malware",
        check_investigation_complete,
        {
            "malware": "malware",
            "infrastructure": "infrastructure",
            "synthesis": "synthesis"
        }
    )
    
    workflow.add_conditional_edges(
        "infrastructure",
        check_investigation_complete,
        {
            "malware": "malware",
            "infrastructure": "infrastructure",
            "synthesis": "synthesis"
        }
    )
    
    # End after synthesis
    workflow.add_edge("synthesis", END)
    
    return workflow


def find_unanalyzed_nodes(nodes: list) -> dict:
    """
    Find nodes that haven't been analyzed by specialist agents.
    
    Args:
        nodes: List of graph nodes
    
    Returns:
        Dictionary with lists of unanalyzed files and network IOCs
    """
    
    unanalyzed = {
        "files": [],
        "network": []
    }
    
    for node in nodes:
        # Skip if already analyzed
        if node.get("analyzed"):
            continue
        
        # Categorize by type
        if node["type"] == "file":
            unanalyzed["files"].append(node["id"])
        elif node["type"] in ["ip", "domain", "url"]:
            unanalyzed["network"].append(node["id"])
    
    return unanalyzed
```

---

### 2.3 Agents

#### 2.3.1 Triage Agent

**File:** `backend/agents/triage.py`

**Purpose:** Initial IOC classification and threat assessment
```python
"""
Triage Agent - IOC Classification and Initial Assessment
"""

import re
from backend.tools.mcp_registry import mcp_registry


def classify_ioc_type(ioc: str) -> str:
    """
    Determine IOC type from string pattern.
    
    Args:
        ioc: The IOC string
    
    Returns:
        IOC type: "file", "ip", "domain", or "url"
    """
    
    # File hash patterns
    if re.match(r'^[a-fA-F0-9]{32}$', ioc):  # MD5
        return "file"
    if re.match(r'^[a-fA-F0-9]{40}$', ioc):  # SHA1
        return "file"
    if re.match(r'^[a-fA-F0-9]{64}$', ioc):  # SHA256
        return "file"
    
    # IP address pattern
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ioc):
        return "ip"
    
    # URL pattern
    if ioc.startswith(("http://", "https://")):
        return "url"
    
    # Default to domain
    return "domain"


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
        
        try:
            gti_result = await mcp_registry.call(
                server="gti",
                tool="lookup_ioc",
                args={"ioc": ioc, "ioc_type": ioc_type}
            )
            
            # Log API call
            logger.log_api_call(
                tool="gti_lookup",
                request={"ioc": ioc, "ioc_type": ioc_type},
                response=gti_result,
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
        verdict = gti_result.get("verdict", "UNKNOWN")
        score = gti_result.get("score", 0)
        malicious_votes = gti_result.get("malicious_votes", 0)
        total_votes = gti_result.get("total_votes", 0)
        
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
```

---

#### 2.3.2 Malware Hunter Agent

**File:** `backend/agents/malware.py`

**Purpose:** Deep behavioral analysis of file IOCs
```python
"""
Malware Hunter Agent - Behavioral Analysis
"""

from backend.tools.mcp_registry import mcp_registry


def node_exists(nodes: list, node_id: str) -> bool:
    """Check if node already exists in graph"""
    return any(node["id"] == node_id for node in nodes)


def create_malware_agent(logger):
    """
    Factory function for malware hunter agent.
    
    Args:
        logger: InvestigationLogger instance
    
    Returns:
        Async agent function
    """
    
    async def malware_agent(state: dict):
        """
        Malware Hunter Agent - Behavioral analysis of files.
        
        Process:
        1. Find unanalyzed file hashes in graph
        2. For each file (up to limit):
           a. Query GTI for behavioral analysis
           b. Extract network IOCs
           c. Extract dropped files
           d. Add nodes/edges to graph
           e. Mark file as analyzed
        """
        
        logger.log("INFO", "malware", "Starting behavioral analysis")
        
        # Step 1: Find unanalyzed file hashes
        files_to_analyze = []
        for node in state["graph_nodes"]:
            if node["type"] == "file" and not node.get("analyzed"):
                files_to_analyze.append(node["id"])
        
        # Limit to prevent explosion
        max_per_iteration = 10
        if len(files_to_analyze) > max_per_iteration:
            logger.log(
                "WARN",
                "malware",
                f"Found {len(files_to_analyze)} files, limiting to {max_per_iteration}"
            )
            files_to_analyze = files_to_analyze[:max_per_iteration]
        
        logger.log("INFO", "malware", f"Analyzing {len(files_to_analyze)} files")
        
        # Step 2: Analyze each file
        for file_hash in files_to_analyze:
            # Check budget before proceeding
            can_continue, reason = state["budget"].can_continue()
            if not can_continue:
                logger.log("WARN", "malware", f"Budget exhausted: {reason}")
                break
            
            logger.log("INFO", "malware", f"Analyzing: {file_hash[:16]}...")
            
            try:
                # Query GTI for behavior
                behavior_result = await mcp_registry.call(
                    server="gti",
                    tool="get_behavior_summary",
                    args={"hash": file_hash}
                )
                
                logger.log_api_call(
                    tool="gti_behavior",
                    request={"hash": file_hash},
                    response=behavior_result,
                    duration=behavior_result.get("_duration", 0)
                )
                
            except Exception as e:
                logger.log("ERROR", "malware", f"Behavior analysis failed for {file_hash}: {e}")
                continue
            
            # Extract IOCs from behavior
            network_iocs = behavior_result.get("network_iocs", [])
            dropped_files = behavior_result.get("files_dropped", [])
            
            logger.log(
                "INFO",
                "malware",
                f"Found {len(network_iocs)} network IOCs, {len(dropped_files)} dropped files"
            )
            
            # Add network IOCs to graph
            for ioc in network_iocs:
                ioc_value = ioc.get("value")
                ioc_type = ioc.get("type")
                
                if not ioc_value or not ioc_type:
                    continue
                
                # Add node if doesn't exist
                if not node_exists(state["graph_nodes"], ioc_value):
                    state["graph_nodes"].append({
                        "id": ioc_value,
                        "type": ioc_type,
                        "analyzed": False
                    })
                    state["budget"].nodes_created += 1
                    
                    logger.log("INFO", "malware", f"Added network IOC: {ioc_value} ({ioc_type})")
                
                # Add edge
                state["graph_edges"].append({
                    "source": file_hash,
                    "target": ioc_value,
                    "relationship": "COMMUNICATES_WITH",
                    "description": f"File {file_hash[:16]}... contacted {ioc_value}"
                })
            
            # Add dropped files to graph
            for dropped_hash in dropped_files:
                if not node_exists(state["graph_nodes"], dropped_hash):
                    state["graph_nodes"].append({
                        "id": dropped_hash,
                        "type": "file",
                        "analyzed": False
                    })
                    state["budget"].nodes_created += 1
                    
                    logger.log("INFO", "malware", f"Added dropped file: {dropped_hash[:16]}...")
                
                # Add edge
                state["graph_edges"].append({
                    "source": file_hash,
                    "target": dropped_hash,
                    "relationship": "DROPPED",
                    "description": f"File {file_hash[:16]}... dropped {dropped_hash[:16]}..."
                })
            
            # Mark file as analyzed
            for node in state["graph_nodes"]:
                if node["id"] == file_hash:
                    node["analyzed"] = True
                    node["behavior"] = behavior_result
                    break
            
            # Update budget
            state["budget"].api_calls_made += 1
        
        # Track agent execution
        state["agents_run"].append("malware")
        logger.log("INFO", "malware", "Behavioral analysis complete")
        
        return state
    
    return malware_agent
```

---

#### 2.3.3 Infrastructure Hunter Agent

**File:** `backend/agents/infrastructure.py`

**Purpose:** Network IOC correlation and infrastructure mapping
```python
"""
Infrastructure Hunter Agent - Network IOC Analysis
"""

from backend.tools.mcp_registry import mcp_registry


def node_exists(nodes: list, node_id: str) -> bool:
    """Check if node already exists in graph"""
    return any(node["id"] == node_id for node in nodes)


def create_infrastructure_agent(logger):
    """
    Factory function for infrastructure hunter agent.
    
    Args:
        logger: InvestigationLogger instance
    
    Returns:
        Async agent function
    """
    
    async def infrastructure_agent(state: dict):
        """
        Infrastructure Hunter Agent - Network IOC analysis.
        
        Process:
        1. Find unanalyzed network IOCs in graph
        2. For each IOC (up to limit):
           a. Query GTI for infrastructure data
           b. Extract related IOCs (passive DNS, etc.)
           c. Add nodes/edges to graph
           d. Mark IOC as analyzed
        """
        
        logger.log("INFO", "infra", "Starting infrastructure analysis")
        
        # Step 1: Find unanalyzed network IOCs
        network_to_analyze = []
        for node in state["graph_nodes"]:
            if node["type"] in ["ip", "domain", "url"] and not node.get("analyzed"):
                network_to_analyze.append(node)
        
        # Limit per iteration
        max_per_iteration = 10
        if len(network_to_analyze) > max_per_iteration:
            logger.log(
                "WARN",
                "infra",
                f"Found {len(network_to_analyze)} IOCs, limiting to {max_per_iteration}"
            )
            network_to_analyze = network_to_analyze[:max_per_iteration]
        
        logger.log("INFO", "infra", f"Analyzing {len(network_to_analyze)} network IOCs")
        
        # Step 2: Analyze each IOC
        for node in network_to_analyze:
            # Check budget
            can_continue, reason = state["budget"].can_continue()
            if not can_continue:
                logger.log("WARN", "infra", f"Budget exhausted: {reason}")
                break
            
            ioc_value = node["id"]
            ioc_type = node["type"]
            
            logger.log("INFO", "infra", f"Analyzing {ioc_type}: {ioc_value}")
            
            # Call appropriate tool based on type
            try:
                if ioc_type == "domain":
                    result = await mcp_registry.call(
                        server="gti",
                        tool="get_domain_report",
                        args={"domain": ioc_value}
                    )
                elif ioc_type == "ip":
                    result = await mcp_registry.call(
                        server="gti",
                        tool="get_ip_report",
                        args={"ip": ioc_value}
                    )
                else:  # URL
                    result = await mcp_registry.call(
                        server="gti",
                        tool="get_url_report",
                        args={"url": ioc_value}
                    )
                
                logger.log_api_call(
                    tool=f"gti_{ioc_type}",
                    request={ioc_type: ioc_value},
                    response=result,
                    duration=result.get("_duration", 0)
                )
                
            except Exception as e:
                logger.log("ERROR", "infra", f"Analysis failed for {ioc_value}: {e}")
                continue
            
            # Extract related IOCs
            related_iocs = result.get("related_iocs", [])
            
            logger.log("INFO", "infra", f"Found {len(related_iocs)} related IOCs")
            
            # Add to graph
            for related in related_iocs:
                related_value = related.get("value")
                related_type = related.get("type")
                relationship = related.get("relationship", "ASSOCIATED_WITH")
                description = related.get("description", "")
                
                if not related_value or not related_type:
                    continue
                
                # Add node
                if not node_exists(state["graph_nodes"], related_value):
                    state["graph_nodes"].append({
                        "id": related_value,
                        "type": related_type,
                        "analyzed": False
                    })
                    state["budget"].nodes_created += 1
                    
                    logger.log("INFO", "infra", f"Added {related_type}: {related_value}")
                
                # Add edge
                state["graph_edges"].append({
                    "source": ioc_value,
                    "target": related_value,
                    "relationship": relationship,
                    "description": description or f"{ioc_value} {relationship} {related_value}"
                })
            
            # Mark as analyzed
            node["analyzed"] = True
            node["infrastructure_data"] = result
            
            # Update budget
            state["budget"].api_calls_made += 1
        
        # Track agent execution
        state["agents_run"].append("infrastructure")
        logger.log("INFO", "infra", "Infrastructure analysis complete")
        
        return state
    
    return infrastructure_agent
```

---

#### 2.3.4 Synthesis Agent

**File:** `backend/agents/synthesis.py`

**Purpose:** Final report generation and graph visualization
```python
"""
Synthesis Agent - Report Generation
"""

import networkx as nx
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
        Synthesis Agent - Generate final investigation report.
        
        Process:
        1. Reconstruct NetworkX graph from state
        2. Generate executive summary
        3. Describe attack chain
        4. List key findings
        5. Identify unanalyzed nodes (if any)
        6. Generate Mermaid graph visualization
        7. Provide recommendations
        """
        
        logger.log("INFO", "synthesis", "Generating final report")
        
        # Step 1: Reconstruct graph
        G = nx.DiGraph()
        for node in state["graph_nodes"]:
            G.add_node(node["id"], **node)
        for edge in state["graph_edges"]:
            G.add_edge(edge["source"], edge["target"], **edge)
        
        # Step 2: Generate report sections
        report = []
        
        # Header
        report.append("# Investigation Report\n")
        report.append(f"**Investigation ID:** {datetime.now().strftime('%Y%m%d_%H%M%S')}\n")
        report.append(f"**IOC:** {state['ioc']}\n")
        report.append(f"**Type:** {state['ioc_type']}\n")
        report.append(f"**Status:** {state['status']}\n")
        report.append(f"**Iterations:** {state['iteration']}\n")
        report.append(f"**Generated:** {datetime.now().isoformat()}\n\n")
        
        # Step 3: Initial verdict
        root_node = next(n for n in state["graph_nodes"] if n["id"] == state["ioc"])
        report.append("## Initial Assessment\n")
        report.append(f"**Verdict:** {root_node.get('verdict', 'UNKNOWN')}\n")
        report.append(f"**Threat Score:** {root_node.get('score', 0)}/100\n")
        report.append(f"**Detections:** {root_node.get('malicious_votes', 0)}/{root_node.get('total_votes', 0)}\n\n")
        
        # Step 4: Attack chain
        report.append("## Attack Chain\n")
        report.append(describe_attack_chain(G, state["ioc"]))
        report.append("\n")
        
        # Step 5: Key findings
        report.append("## Key Findings\n")
        malicious_nodes = [n for n in state["graph_nodes"] if n.get("verdict") == "MALICIOUS"]
        suspicious_nodes = [n for n in state["graph_nodes"] if n.get("verdict") == "SUSPICIOUS"]
        
        report.append(f"- **Total IOCs Discovered:** {len(state['graph_nodes'])}\n")
        report.append(f"- **Malicious IOCs:** {len(malicious_nodes)}\n")
        report.append(f"- **Suspicious IOCs:** {len(suspicious_nodes)}\n")
        report.append(f"- **API Calls Made:** {state['budget'].api_calls_made}\n")
        report.append(f"- **Agents Run:** {', '.join(state['agents_run'])}\n\n")
        
        # Step 6: Unanalyzed nodes (if any)
        unanalyzed = [n for n in state["graph_nodes"] if not n.get("analyzed")]
        if unanalyzed:
            report.append("## ⚠️ Incomplete Analysis\n")
            report.append(f"The following {len(unanalyzed)} IOCs were not fully analyzed:\n\n")
            for node in unanalyzed[:10]:
                report.append(f"- `{node['id']}` ({node['type']})\n")
            if len(unanalyzed) > 10:
                report.append(f"- ... and {len(unanalyzed) - 10} more\n")
            report.append("\n**Recommendation:** Re-run investigation with higher limits.\n\n")
        
        # Step 7: Graph visualization
        report.append("## Investigation Graph Visualization\n")
        report.append("```mermaid\n")
        report.append(generate_mermaid_graph(G))
        report.append("\n```\n\n")
        
        # Step 8: Recommendations
        report.append("## Recommendations\n")
        if root_node.get("verdict") == "MALICIOUS":
            report.append("- ⛔ **BLOCK** this IOC immediately\n")
            report.append("- 🔍 **Hunt** for related IOCs in your environment\n")
            report.append("- 📊 **Monitor** for similar patterns\n")
            report.append("- 🚨 **Alert** SOC team for incident response\n")
        elif root_node.get("verdict") == "SUSPICIOUS":
            report.append("- 👀 **Monitor** this IOC closely\n")
            report.append("- 🔍 **Investigate** related activity\n")
            report.append("- 📊 **Track** for pattern changes\n")
        else:
            report.append("- ✅ **No immediate action** required\n")
            report.append("- 📊 **Continue monitoring** for changes\n")
        
        # Compile report
        state["report"] = "\n".join(report)
        state["status"] = "complete"
        
        # Track agent execution
        state["agents_run"].append("synthesis")
        logger.log("INFO", "synthesis", "Report generation complete")
        
        return state
    
    return synthesis_agent


def describe_attack_chain(G: nx.DiGraph, root_ioc: str) -> str:
    """
    Generate narrative description of attack chain.
    
    Args:
        G: NetworkX graph
        root_ioc: Root IOC value
    
    Returns:
        Markdown-formatted attack chain description
    """
    
    chain = []
    chain.append(f"1. **Initial IOC:** `{root_ioc}`\n")
    
    # Find dropped files
    dropped = [
        (target, data)
        for source, target, data in G.edges(root_ioc, data=True)
        if data.get("relationship") == "DROPPED"
    ]
    
    if dropped:
        chain.append(f"2. **Dropped Files:** {len(dropped)} file(s)\n")
        for target, data in dropped[:3]:
            chain.append(f"   - `{target}` - {data.get('description', 'No description')}\n")
        if len(dropped) > 3:
            chain.append(f"   - ... and {len(dropped) - 3} more\n")
    
    # Find C2 communications
    c2 = [
        (target, data)
        for source, target, data in G.edges(root_ioc, data=True)
        if data.get("relationship") == "COMMUNICATES_WITH"
    ]
    
    if c2:
        chain.append(f"3. **C2 Infrastructure:** {len(c2)} IOC(s)\n")
        for target, data in c2[:3]:
            chain.append(f"   - `{target}` - {data.get('description', 'No description')}\n")
        if len(c2) > 3:
            chain.append(f"   - ... and {len(c2) - 3} more\n")
    
    return "".join(chain)


def generate_mermaid_graph(G: nx.DiGraph) -> str:
    """
    Convert NetworkX graph to Mermaid syntax.
    
    Args:
        G: NetworkX graph
    
    Returns:
        Mermaid diagram as string
    """
    
    if G.number_of_nodes() == 0:
        return "graph TD;\n    Empty[No Data Available]"
    
    lines = ["graph TD"]
    
    # Add styling
    lines.append("    %% Node Styling")
    lines.append("    classDef malicious fill:#ff4d4d,color:white,stroke:#333;")
    lines.append("    classDef suspicious fill:#ffad33,color:white,stroke:#333;")
    lines.append("    classDef clean fill:#4dff4d,color:black,stroke:#333;")
    lines.append("    classDef unknown fill:#cccccc,color:black,stroke:#333;")
    
    # Sanitize ID function
    def safe_id(val):
        # Replace problematic characters and truncate
        safe = val.replace('.', '_').replace(':', '_').replace('-', '_')
        return safe[:30]
    
    # Add nodes
    for node_id, attrs in G.nodes(data=True):
        safe_node_id = safe_id(node_id)
        node_type = attrs.get('type', 'unknown')
        
        # Truncate label for readability
        label_text = node_id if len(node_id) <= 20 else node_id[:17] + "..."
        label = f"{label_text}\\n({node_type})"
        
        # Determine style class
        verdict = attrs.get("verdict", "UNKNOWN")
        if verdict == "MALICIOUS":
            style_class = ":::malicious"
        elif verdict == "SUSPICIOUS":
            style_class = ":::suspicious"
        elif verdict == "BENIGN":
            style_class = ":::clean"
        else:
            style_class = ":::unknown"
        
        lines.append(f'    {safe_node_id}["{label}"]{style_class}')
    
    # Add edges
    for source, target, attrs in G.edges(data=True):
        safe_source = safe_id(source)
        safe_target = safe_id(target)
        rel = attrs.get('relationship', 'RELATED')
        
        # Edge label
        edge_label = f"|{rel}|"
        
        lines.append(f'    {safe_source}-->{edge_label}{safe_target}')
    
    return "\n".join(lines)
```

---

### 2.4 Supporting Infrastructure

#### 2.4.1 Investigation Budget

**File:** `backend/models.py`

**Purpose:** Data models and budget tracking
```python
"""
Data Models for Threat Hunter Platform
"""

from typing import TypedDict, Optional
from dataclasses import dataclass, field
import time


class InvestigationState(TypedDict):
    """LangGraph state for investigations"""
    
    # Input
    ioc: str
    ioc_type: str
    
    # Graph (serialized as lists)
    graph_nodes: list[dict]
    graph_edges: list[dict]
    
    # Control flow
    iteration: int
    max_iterations: int
    agents_run: list[str]
    status: str
    verdict: str  # For routing decisions
    
    # Budget tracking
    budget: 'InvestigationBudget'
    
    # Output
    findings: list[dict]
    report: str


@dataclass
class InvestigationBudget:
    """
    Track and enforce resource limits during investigation.
    
    Prevents:
    - Infinite loops (max iterations)
    - Graph explosions (max nodes)
    - API cost explosions (max API calls)
    - Hung investigations (max wall time)
    """
    
    # Limits
    max_api_calls: int = 200
    max_graph_nodes: int = 50
    max_wall_time: int = 600  # 10 minutes in seconds
    
    # Counters
    api_calls_made: int = 0
    nodes_created: int = 0
    start_time: float = field(default_factory=time.time)
    
    def can_continue(self) -> tuple[bool, Optional[str]]:
        """
        Check if investigation can continue.
        
        Returns:
            Tuple of (can_continue, reason)
            - can_continue: True if investigation can proceed
            - reason: If False, explanation of why it cannot continue
        """
        
        # Check API call limit
        if self.api_calls_made >= self.max_api_calls:
            return False, f"API call limit reached ({self.api_calls_made}/{self.max_api_calls})"
        
        # Check graph node limit
        if self.nodes_created >= self.max_graph_nodes:
            return False, f"Graph node limit reached ({self.nodes_created}/{self.max_graph_nodes})"
        
        # Check wall time limit
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_wall_time:
            return False, f"Investigation timeout ({int(elapsed)}s/{self.max_wall_time}s)"
        
        return True, None
    
    def to_dict(self) -> dict:
        """Serialize budget for logging"""
        elapsed = int(time.time() - self.start_time)
        
        return {
            "api_calls": f"{self.api_calls_made}/{self.max_api_calls}",
            "nodes": f"{self.nodes_created}/{self.max_graph_nodes}",
            "elapsed": f"{elapsed}s/{self.max_wall_time}s",
            "can_continue": self.can_continue()[0]
        }
```

#### 2.4.2 MCP Registry

**File:** `backend/tools/mcp_registry.py`

**Purpose:** Manage connections to MCP servers and route tool calls
```python
"""
MCP Registry - Tool Connection Management
"""

import os
import asyncio
import httpx
from typing import Dict, Any


class MCPRegistry:
    """
    Manages connections to MCP servers and routes tool calls.
    
    In Phase 1, connects to user's existing MCP servers:
    - GTI MCP Server (Google Threat Intelligence)
    - Shodan MCP Server (optional)
    """
    
    def __init__(self):
        self.servers = {
            "gti": {
                "url": os.getenv("GTI_MCP_URL", "http://localhost:3001"),
                "capabilities": [
                    "lookup_ioc",
                    "get_behavior_summary",
                    "get_domain_report",
                    "get_ip_report",
                    "get_url_report"
                ]
            },
            "shodan": {
                "url": os.getenv("SHODAN_MCP_URL", "http://localhost:3002"),
                "capabilities": ["ip_lookup", "search"]
            }
        }
        
        # HTTP client for MCP communication
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def call(self, server: str, tool: str, args: dict) -> dict:
        """
        Route tool call to appropriate MCP server.
        
        Args:
            server: Server name (e.g., "gti", "shodan")
            tool: Tool name (e.g., "lookup_ioc", "get_behavior_summary")
            args: Tool arguments as dictionary
        
        Returns:
            Tool response as dictionary
        
        Raises:
            ValueError: If server or tool not found
            Exception: If API call fails
        """
        
        # Validate server exists
        if server not in self.servers:
            raise ValueError(f"Unknown server: {server}")
        
        server_config = self.servers[server]
        
        # Validate tool capability
        if tool not in server_config["capabilities"]:
            raise ValueError(f"Server {server} doesn't support tool {tool}")
        
        # Prepare MCP request
        url = f"{server_config['url']}/tools/{tool}"
        
        # Make HTTP call
        import time
        start_time = time.time()
        
        try:
            response = await self.client.post(
                url,
                json={"arguments": args}
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Add duration for logging
            duration = time.time() - start_time
            result["_duration"] = duration
            
            return result
            
        except httpx.HTTPError as e:
            raise Exception(f"MCP call failed: {server}/{tool} - {str(e)}")
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Global registry instance
mcp_registry = MCPRegistry()
```

---

#### 2.4.3 Logging System

**File:** `backend/logging_config.py`

**Purpose:** Two-tier logging infrastructure
```python
"""
Two-Tier Logging System
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class InvestigationLogger:
    """
    Two-tier logging system for investigations.
    
    Tier 1 (Normal): Always on, captures decisions and flow
    Tier 2 (Debug): Opt-in, captures full prompts/APIs/state
    """
    
    def __init__(self, investigation_id: str, debug_mode: bool = False):
        self.investigation_id = investigation_id
        self.debug_mode = debug_mode
        self.call_counter = 0
        
        # Setup directories
        self.log_dir = Path("logs")
        self.normal_log = self.log_dir / "normal" / f"investigation_{investigation_id}.log"
        self.normal_log.parent.mkdir(parents=True, exist_ok=True)
        
        if debug_mode:
            self.debug_log = self.log_dir / "debug" / f"investigation_{investigation_id}.log"
            self.llm_dir = self.log_dir / "debug" / f"{investigation_id}_llm_prompts"
            self.api_dir = self.log_dir / "debug" / f"{investigation_id}_api_calls"
            self.state_dir = self.log_dir / "debug" / f"{investigation_id}_state_snapshots"
            
            for d in [self.llm_dir, self.api_dir, self.state_dir]:
                d.mkdir(parents=True, exist_ok=True)
    
    def log(self, level: str, agent: str, message: str, context: dict = None):
        """
        Normal logging - always enabled.
        
        Args:
            level: Log level (INFO, WARN, ERROR, DECISION)
            agent: Agent name (triage, malware, infra, synthesis, system)
            message: Log message
            context: Optional context dictionary
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{self.investigation_id}] [{agent}] {level}: {message}\n"
        
        # Write to file
        with open(self.normal_log, "a") as f:
            f.write(log_line)
        
        # Print to console
        print(log_line.strip())
        
        # Debug mode: also write structured JSON
        if self.debug_mode and context:
            debug_entry = {
                "timestamp": timestamp,
                "investigation_id": self.investigation_id,
                "agent": agent,
                "level": level,
                "message": message,
                "context": context
            }
            with open(self.debug_log, "a") as f:
                f.write(json.dumps(debug_entry) + "\n")
    
    def log_decision(self, agent: str, decision: str, reasoning: str):
        """
        Log agent decision points.
        
        Args:
            agent: Agent name
            decision: Decision made
            reasoning: Explanation for decision
        """
        self.log("DECISION", agent, decision, {"reasoning": reasoning})
    
    def log_api_call(self, tool: str, request: dict, response: dict, duration: float):
        """
        Log API calls.
        
        Normal mode: Just summary
        Debug mode: Full request/response payloads
        
        Args:
            tool: Tool name (e.g., "gti_lookup", "gti_behavior")
            request: Request payload
            response: Response payload
            duration: Call duration in seconds
        """
        
        # Normal log: summary only
        self.log("INFO", "tool", f"Called {tool} (took {duration:.2f}s)")
        
        # Debug mode: save full payloads
        if self.debug_mode:
            self.call_counter += 1
            prefix = f"{self.call_counter:03d}_{tool}"
            
            req_file = self.api_dir / f"{prefix}_request.json"
            resp_file = self.api_dir / f"{prefix}_response.json"
            
            req_file.write_text(json.dumps(request, indent=2, default=str))
            resp_file.write_text(json.dumps(response, indent=2, default=str))
            
            self.log("DEBUG", "tool", f"API call {tool}", {
                "call_number": self.call_counter,
                "duration": duration,
                "request_file": str(req_file),
                "response_file": str(resp_file)
            })
    
    def log_llm_interaction(self, agent: str, prompt: str, response: str,
                           model: str, tokens: dict):
        """
        Debug mode only: Save full LLM prompts/responses.
        
        Args:
            agent: Agent name
            prompt: Full LLM prompt
            response: Full LLM response
            model: Model name (e.g., "gemini-2.0-flash")
            tokens: Token counts {"prompt": X, "completion": Y}
        """
        if not self.debug_mode:
            return
        
        self.call_counter += 1
        prefix = f"{self.call_counter:03d}_{agent}"
        
        prompt_file = self.llm_dir / f"{prefix}_prompt.txt"
        response_file = self.llm_dir / f"{prefix}_response.txt"
        
        prompt_file.write_text(prompt)
        response_file.write_text(response)
        
        self.log("DEBUG", agent, "LLM interaction", {
            "model": model,
            "prompt_tokens": tokens.get("prompt", 0),
            "completion_tokens": tokens.get("completion", 0),
            "prompt_file": str(prompt_file),
            "response_file": str(response_file)
        })
    
    def log_state_snapshot(self, stage: str, state: dict):
        """
        Debug mode only: Save LangGraph state snapshot.
        
        Args:
            stage: Stage name (e.g., "after_triage", "after_malware")
            state: Complete investigation state
        """
        if not self.debug_mode:
            return
        
        snapshot_file = self.state_dir / f"{stage}.json"
        snapshot_file.write_text(json.dumps(state, indent=2, default=str))
        
        self.log("DEBUG", "system", f"State snapshot: {stage}", {
            "file": str(snapshot_file),
            "nodes": len(state.get("graph_nodes", [])),
            "edges": len(state.get("graph_edges", [])),
            "iteration": state.get("iteration", 0)
        })
```

---

## 3. Helper Functions

### 3.1 Graph Utilities

**File:** `backend/utils/graph_utils.py`

**Purpose:** Common graph operations
```python
"""
Graph Utility Functions
"""


def node_exists(nodes: list, node_id: str) -> bool:
    """
    Check if node already exists in graph.
    
    Args:
        nodes: List of graph nodes
        node_id: Node ID to check
    
    Returns:
        True if node exists, False otherwise
    """
    return any(node["id"] == node_id for node in nodes)


def find_unanalyzed_nodes(nodes: list) -> dict:
    """
    Find nodes that haven't been analyzed by specialist agents.
    
    Args:
        nodes: List of graph nodes
    
    Returns:
        Dictionary with lists of unanalyzed files and network IOCs
        {
            "files": ["hash1", "hash2", ...],
            "network": ["ip1", "domain1", ...]
        }
    """
    
    unanalyzed = {
        "files": [],
        "network": []
    }
    
    for node in nodes:
        # Skip if already analyzed
        if node.get("analyzed"):
            continue
        
        # Categorize by type
        if node["type"] == "file":
            unanalyzed["files"].append(node["id"])
        elif node["type"] in ["ip", "domain", "url"]:
            unanalyzed["network"].append(node["id"])
    
    return unanalyzed


def would_create_cycle(edges: list, source: str, target: str) -> bool:
    """
    Check if adding an edge would create a cycle.
    
    This is a safety check to prevent circular references in the graph.
    
    Args:
        edges: List of existing graph edges
        source: Proposed edge source
        target: Proposed edge target
    
    Returns:
        True if edge would create cycle, False otherwise
    """
    
    # Build adjacency list
    adj = {}
    for edge in edges:
        adj.setdefault(edge["source"], []).append(edge["target"])
    
    # Check if path exists from target to source (would create cycle)
    def has_path(start, end, visited):
        if start == end:
            return True
        visited.add(start)
        for neighbor in adj.get(start, []):
            if neighbor not in visited:
                if has_path(neighbor, end, visited):
                    return True
        return False
    
    return has_path(target, source, set())


def get_node_by_id(nodes: list, node_id: str) -> dict:
    """
    Get node from graph by ID.
    
    Args:
        nodes: List of graph nodes
        node_id: Node ID to find
    
    Returns:
        Node dictionary or None if not found
    """
    for node in nodes:
        if node["id"] == node_id:
            return node
    return None


def count_nodes_by_type(nodes: list) -> dict:
    """
    Count nodes by IOC type.
    
    Args:
        nodes: List of graph nodes
    
    Returns:
        Dictionary mapping type to count
        {"file": 5, "ip": 3, "domain": 2, "url": 1}
    """
    counts = {}
    for node in nodes:
        node_type = node.get("type", "unknown")
        counts[node_type] = counts.get(node_type, 0) + 1
    return counts


def count_nodes_by_verdict(nodes: list) -> dict:
    """
    Count nodes by verdict.
    
    Args:
        nodes: List of graph nodes
    
    Returns:
        Dictionary mapping verdict to count
        {"MALICIOUS": 3, "SUSPICIOUS": 1, "BENIGN": 2}
    """
    counts = {}
    for node in nodes:
        verdict = node.get("verdict", "UNKNOWN")
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts
```

---

### 3.2 IOC Classification

**File:** `backend/utils/ioc_utils.py`

**Purpose:** IOC type detection and validation
```python
"""
IOC Utility Functions
"""

import re
from urllib.parse import urlparse


def classify_ioc_type(ioc: str) -> str:
    """
    Determine IOC type from string pattern.
    
    Args:
        ioc: The IOC string
    
    Returns:
        IOC type: "file", "ip", "domain", or "url"
    """
    
    # File hash patterns
    if re.match(r'^[a-fA-F0-9]{32}$', ioc):  # MD5
        return "file"
    if re.match(r'^[a-fA-F0-9]{40}$', ioc):  # SHA1
        return "file"
    if re.match(r'^[a-fA-F0-9]{64}$', ioc):  # SHA256
        return "file"
    
    # IP address pattern
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ioc):
        return "ip"
    
    # URL pattern
    if ioc.startswith(("http://", "https://")):
        return "url"
    
    # Default to domain
    return "domain"


def extract_domain_from_url(url: str) -> str:
    """
    Extract domain from URL.
    
    Args:
        url: URL string
    
    Returns:
        Domain or empty string if extraction fails
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except:
        return ""


def is_valid_hash(hash_value: str, hash_type: str = "sha256") -> bool:
    """
    Validate hash format.
    
    Args:
        hash_value: Hash string
        hash_type: Hash type ("md5", "sha1", "sha256")
    
    Returns:
        True if valid format, False otherwise
    """
    patterns = {
        "md5": r'^[a-fA-F0-9]{32}$',
        "sha1": r'^[a-fA-F0-9]{40}$',
        "sha256": r'^[a-fA-F0-9]{64}$'
    }
    
    pattern = patterns.get(hash_type.lower())
    if not pattern:
        return False
    
    return bool(re.match(pattern, hash_value))


def is_valid_ip(ip: str) -> bool:
    """
    Validate IPv4 address format.
    
    Args:
        ip: IP address string
    
    Returns:
        True if valid IPv4, False otherwise
    """
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        return False
    
    # Check octets are 0-255
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)


def truncate_ioc(ioc: str, max_length: int = 50) -> str:
    """
    Truncate IOC for display purposes.
    
    Args:
        ioc: IOC string
        max_length: Maximum length
    
    Returns:
        Truncated IOC with ellipsis if needed
    """
    if len(ioc) <= max_length:
        return ioc
    
    return ioc[:max_length-3] + "..."
```

---

## 4. Implementation Checklist

### Week 1: Foundation (Days 1-7)

**Days 1-2: Project Setup**
- [ ] Create project directory structure
- [ ] Initialize git repository
- [ ] Create virtual environment
- [ ] Install dependencies (`requirements.txt`)
- [ ] Set up `.env` file with API keys
- [ ] Create `.gitignore`
- [ ] Write `README.md`

**Days 3-4: Logging Infrastructure**
- [ ] Implement `InvestigationLogger` class
- [ ] Test normal logging (file + console)
- [ ] Test debug logging (prompts, APIs, state)
- [ ] Verify log directory creation
- [ ] Test log file rotation/naming

**Days 5: MCP Registry**
- [ ] Implement `MCPRegistry` class
- [ ] Test connection to GTI MCP server
- [ ] Test tool call routing
- [ ] Add error handling for failed connections
- [ ] Add timeout handling

**Days 6-7: Triage Agent & Graph Utilities**
- [ ] Implement `classify_ioc_type()`
- [ ] Implement `create_triage_agent()`
- [ ] Test with sample IOCs (file, IP, domain, URL)
- [ ] Implement graph utility functions
- [ ] Test node creation and deduplication

---

### Week 2: Core Agents (Days 8-14)

**Days 8-10: Malware Hunter Agent**
- [ ] Implement `create_malware_agent()`
- [ ] Test with known malware samples
- [ ] Verify network IOC extraction
- [ ] Verify dropped file extraction
- [ ] Test graph edge creation
- [ ] Add comprehensive logging

**Days 11-12: Infrastructure Hunter Agent**
- [ ] Implement `create_infrastructure_agent()`
- [ ] Test with domains
- [ ] Test with IP addresses
- [ ] Test with URLs
- [ ] Verify passive DNS extraction
- [ ] Add comprehensive logging

**Days 13-14: Integration Testing**
- [ ] Test full workflow (triage → malware → infrastructure)
- [ ] Verify graph builds correctly
- [ ] Test iteration logic
- [ ] Verify budget limits work
- [ ] Test with various IOC types

---

### Week 3: Synthesis & Benchmarking (Days 15-21)

**Days 15-17: Synthesis Agent**
- [ ] Implement `create_synthesis_agent()`
- [ ] Implement `describe_attack_chain()`
- [ ] Implement `generate_mermaid_graph()`
- [ ] Test report generation
- [ ] Verify Mermaid syntax is valid
- [ ] Test with complex graphs (20+ nodes)

**Days 18-19: CLI Interface**
- [ ] Implement `cli.py`
- [ ] Test with various IOCs
- [ ] Test debug mode flag
- [ ] Add progress indicators
- [ ] Test error handling
- [ ] Verify report/graph file outputs

**Days 20-21: Benchmarking**
- [ ] Create benchmark test suite (see BENCHMARKING_GUIDE.md)
- [ ] Run benchmarks on 50+ IOCs
- [ ] Analyze results
- [ ] Calculate recommended timeout values
- [ ] Document findings in `docs/benchmarks.md`

---

### Post-Week 3: Documentation & Polish

- [ ] Update `README.md` with usage examples
- [ ] Write `docs/USAGE.md` with CLI examples
- [ ] Document common errors and solutions
- [ ] Create `CONTRIBUTING.md` (if open-sourcing)
- [ ] Review all code comments
- [ ] Run final end-to-end tests

---

## 5. Testing Guidelines

### Unit Testing

Create tests in `tests/` directory:
```python
# tests/test_triage.py

import pytest
from backend.agents.triage import classify_ioc_type, create_triage_agent
from backend.logging_config import InvestigationLogger
from backend.models import InvestigationBudget


def test_classify_file_hash_md5():
    ioc = "d41d8cd98f00b204e9800998ecf8427e"
    assert classify_ioc_type(ioc) == "file"


def test_classify_file_hash_sha256():
    ioc = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert classify_ioc_type(ioc) == "file"


def test_classify_ip_address():
    ioc = "192.168.1.1"
    assert classify_ioc_type(ioc) == "ip"


def test_classify_domain():
    ioc = "example.com"
    assert classify_ioc_type(ioc) == "domain"


def test_classify_url():
    ioc = "https://example.com/malicious"
    assert classify_ioc_type(ioc) == "url"


@pytest.mark.asyncio
async def test_triage_agent_basic():
    """Test triage agent with mock MCP"""
    
    logger = InvestigationLogger("test-001", debug_mode=False)
    agent = create_triage_agent(logger)
    
    # Mock state
    state = {
        "ioc": "d41d8cd98f00b204e9800998ecf8427e",
        "ioc_type": "",
        "graph_nodes": [],
        "graph_edges": [],
        "budget": InvestigationBudget(),
        "agents_run": [],
        "findings": []
    }
    
    # TODO: Mock MCP response
    # result = await agent(state)
    
    # assert result["ioc_type"] == "file"
    # assert len(result["graph_nodes"]) == 1
```

### Integration Testing
```python
# tests/test_workflow.py

import pytest
from backend.graph_workflow import create_investigation_workflow
from backend.logging_config import InvestigationLogger


@pytest.mark.asyncio
async def test_full_investigation_file():
    """Test complete investigation of file hash"""
    
    logger = InvestigationLogger("test-002", debug_mode=True)
    workflow = create_investigation_workflow(logger)
    app = workflow.compile()
    
    # Test with known file hash
    result = await app.ainvoke({
        "ioc": "known_malware_hash",
        "ioc_type": "",
        "iteration": 0,
        "graph_nodes": [],
        "graph_edges": [],
        # ... rest of state
    })
    
    # Verify
    assert "triage" in result["agents_run"]
    assert "malware" in result["agents_run"]
    assert len(result["graph_nodes"]) > 1
    assert result["status"] == "complete"
```

---

## 6. Debugging Workflows

### Scenario: Agent Made Wrong Decision

**Steps:**
1. Get investigation ID from CLI output
2. Open `logs/debug/investigation_{id}.log`
3. Search for `DECISION` entries for that agent
4. Check `{id}_llm_prompts/` for exact prompt
5. Check `{id}_api_calls/` for API data
6. Identify if issue is in prompt or data

**Example:**
```bash
# Find decision
grep "DECISION.*triage" logs/debug/investigation_inv-123.log

# Read prompt
cat logs/debug/inv-123_llm_prompts/001_triage_prompt.txt

# Check API response
cat logs/debug/inv-123_api_calls/001_gti_response.json
```

---

### Scenario: Investigation Got Stuck

**Steps:**
1. Check last log entry to see where it stopped
2. Look for timeout errors or budget exhaustion
3. Check state snapshot to see iteration count
4. Verify MCP server is running

**Example:**
```bash
# See last entries
tail -n 20 logs/normal/investigation_inv-123.log

# Check for budget issues
grep "Budget" logs/normal/investigation_inv-123.log

# View final state
cat logs/debug/inv-123_state_snapshots/after_malware.json
```

---

### Scenario: Graph Has Missing Nodes

**Steps:**
1. Check if nodes were added but marked as `analyzed=False`
2. Verify budget limits didn't prevent analysis
3. Check agent logic for node creation conditions
4. Look for errors in API calls

**Example:**
```python
# In synthesis agent
unanalyzed = [n for n in state["graph_nodes"] if not n.get("analyzed")]
if unanalyzed:
    logger.log("WARN", "synthesis", f"Found {len(unanalyzed)} unanalyzed nodes")
    # Log which ones and why
```

---

## 7. Common Patterns & Anti-Patterns

### ✅ DO: Check Budget Before Expensive Operations
```python
# Good
can_continue, reason = state["budget"].can_continue()
if not can_continue:
    logger.log("WARN", agent, f"Budget exhausted: {reason}")
    return state

# Then proceed with API call
result = await mcp_registry.call(...)
```

### ❌ DON'T: Assume API Calls Succeed
```python
# Bad
result = await mcp_registry.call(...)
score = result["score"]  # Crashes if key missing!

# Good
try:
    result = await mcp_registry.call(...)
    score = result.get("score", 0)
except Exception as e:
    logger.log("ERROR", agent, f"API call failed: {e}")
    # Handle gracefully
```

### ✅ DO: Log Every Decision
```python
# Good
logger.log_decision(
    agent="triage",
    decision="Route to Malware Hunter",
    reasoning=f"Verdict: {verdict}, Type: file"
)
```

### ❌ DON'T: Create Circular References
```python
# Bad
state["graph_edges"].append({"source": "A", "target": "B"})
state["graph_edges"].append({"source": "B", "target": "A"})  # Cycle!

# Good - check first
if not would_create_cycle(state["graph_edges"], source, target):
    state["graph_edges"].append(...)
```

---

## 8. Performance Considerations

### Node Limits Per Iteration
```python
# Prevent explosion in single iteration
max_per_iteration = 10

files_to_analyze = get_unanalyzed_files()
if len(files_to_analyze) > max_per_iteration:
    files_to_analyze = files_to_analyze[:max_per_iteration]
```

### API Call Batching

For Phase 1, sequential API calls are fine. For Phase 2+, consider:
```python
# Future optimization (Phase 2+)
import asyncio

# Batch API calls
tasks = [
    mcp_registry.call("gti", "lookup_ioc", {"ioc": ioc})
    for ioc in iocs[:5]  # Batch of 5
]

results = await asyncio.gather(*tasks)
```

---

## Appendix A: Complete File Listing
```
backend/
├── __init__.py
├── cli.py                      # CLI entry point (§2.1)
├── graph_workflow.py           # LangGraph workflow (§2.2)
├── models.py                   # Data models (§2.4.1)
├── logging_config.py           # Logging system (§2.4.3)
│
├── agents/
│   ├── __init__.py
│   ├── triage.py               # Triage agent (§2.3.1)
│   ├── malware.py              # Malware hunter (§2.3.2)
│   ├── infrastructure.py       # Infrastructure hunter (§2.3.3)
│   └── synthesis.py            # Synthesis agent (§2.3.4)
│
├── tools/
│   ├── __init__.py
│   └── mcp_registry.py         # MCP registry (§2.4.2)
│
└── utils/
    ├── __init__.py
    ├── graph_utils.py          # Graph utilities (§3.1)
    └── ioc_utils.py            # IOC utilities (§3.2)
```

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Maintained By:** Development Team  
**Related Docs:** [PRD.md](./PRD.md), [BENCHMARKING_GUIDE.md](./BENCHMARKING_GUIDE.md), [CLAUDE.md](./CLAUDE.md)