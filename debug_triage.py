import asyncio
import os
import sys

# Ensure backend can be imported
sys.path.append(os.getcwd())

from backend.agents.triage import triage_node
from backend.utils.logger import configure_logger

configure_logger()

async def test_triage():
    print("Testing triage_node locally...")
    state = {
        "ioc": "1a4a3bfb72f3a80e4b499ecebe99f53a2b7785eace7f612b3e219409d1e1ffc7",
        "metadata": {"tool_call_trace": {}}
    }
    try:
        result = await triage_node(state)
        print("Success!")
        print(result.keys())
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_triage())
