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
