import sys
import os
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.models import InvestigationBudget
from backend.agents.triage import create_triage_agent

# Mock Logger
class MockLogger:
    def log(self, level, agent, message, context=None):
        print(f"[{level}] {agent}: {message}")
    def log_decision(self, agent, decision, reasoning):
        print(f"[DECISION] {agent}: {decision} ({reasoning})")
    def log_api_call(self, tool, request, response, duration):
        print(f"[API] {tool} called")

async def test_triage():
    print("--- Testing Triage Agent (with Parser) ---")
    
    # Mock MCP Registry - we patch the global instance used in the module
    with patch('backend.agents.triage.mcp_registry') as mock_registry:
        # Configure call method to be async
        mock_registry.call = AsyncMock()
        
        logger = MockLogger()
        agent = create_triage_agent(logger)

        # 1. Test Malicious File
        print("\nTest Case 1: Malicious File")
        # Setup mock return (Raw GTI Structure)
        mock_registry.call.return_value = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 60, "harmless": 10},
                    "gti_assessment": {
                        "verdict": {"value": "MALICIOUS"},
                        "threat_score": {"value": 95}
                    }
                }
            },
            "_duration": 0.5
        }
        
        state1 = {
            "ioc": "d41d8cd98f00b204e9800998ecf8427e",
            "graph_nodes": [],
            "agents_run": [],
            "findings": [],
            "status": "running",
            "budget": InvestigationBudget()
        }
        
        result1 = await agent(state1)
        
        print(f"Input: {state1['ioc']}")
        print(f"Detected Type: {result1['ioc_type']}")
        print(f"Verdict: {result1['verdict']}")
        print(f"Routing Decision: {result1['findings'][0]['decision']}")

        # 2. Test Benign Domain
        print("\nTest Case 2: Benign Domain")
        mock_registry.call.return_value = {
             "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 0, "harmless": 90},
                    "gti_assessment": {
                        "verdict": {"value": "BENIGN"}, # Explicit benign
                        "threat_score": {"value": 0}
                    }
                }
            },
            "_duration": 0.3
        }
        
        state2 = {
            "ioc": "google.com",
            "graph_nodes": [],
            "agents_run": [],
            "findings": [],
            "status": "running",
            "budget": InvestigationBudget()
        }
        
        result2 = await agent(state2)
        
        print(f"Input: {state2['ioc']}")
        print(f"Detected Type: {result2['ioc_type']}")
        print(f"Verdict: {result2['verdict']}")
        print(f"Routing Decision: {result2['findings'][0]['decision']}")

        # 3. Test Suspicious IP
        print("\nTest Case 3: Suspicious IP")
        
        # Determine Suspicious based on stats if GTI verdict is missing/weird
        mock_registry.call.return_value = {
             "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 5, "suspicious": 2},
                    # No explicitly gti_assessment verdict, simpler structure
                }
            },
            "_duration": 0.4
        }

        state3 = {
            "ioc": "1.2.3.4",
            "graph_nodes": [],
            "agents_run": [],
            "findings": [],
            "status": "running",
            "budget": InvestigationBudget()
        }

        result3 = await agent(state3)

        print(f"Input: {state3['ioc']}")
        print(f"Detected Type: {result3['ioc_type']}")
        print(f"Verdict: {result3['verdict']}")
        print(f"Routing Decision: {result3['findings'][0]['decision']}")

if __name__ == "__main__":
    asyncio.run(test_triage())
