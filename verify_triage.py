import asyncio
import os
import json
from dotenv import load_dotenv

# Load env vars (GOOGLE_CLOUD_PROJECT, etc)
load_dotenv()

# Mock State
mock_state = {
    "ioc": "1.1.1.1", # Default test IOC
    "metadata": {"rich_intel": {}},
    "subtasks": []
}

async def run_verification():
    print(f"--- Starting Triage Verification for IOC: {mock_state['ioc']} ---")
    
    # Import here to avoid early failures
    try:
        from backend.agents.triage import triage_node
    except ImportError as e:
        print(f"Error importing triage_node: {e}")
        return

    # Check Env
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("WARNING: GOOGLE_CLOUD_PROJECT not set. LLM call may fail.")

    try:
        # Run Node
        result_state = await triage_node(mock_state)
        
        print("\n--- Triage Agent Result ---")
        print(f"IOC Type: {result_state.get('ioc_type')}")
        print(f"Risk Level: {result_state['metadata'].get('risk_level')}")
        print(f"GTI Score: {result_state['metadata'].get('gti_score')}")
        
        print("\n--- Generated Subtasks ---")
        print(json.dumps(result_state.get("subtasks", []), indent=2))
        
        print("\n--- Rich Intel Context ---")
        intel = result_state['metadata'].get("rich_intel", {})
        print(json.dumps(intel, indent=2))
        
    except Exception as e:
        print(f"RUNTIME ERROR: {e}")

if __name__ == "__main__":
    # Allow command line arg for IOC
    import sys
    if len(sys.argv) > 1:
        mock_state["ioc"] = sys.argv[1]
    
    asyncio.run(run_verification())
