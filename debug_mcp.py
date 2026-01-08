import asyncio
import os
import sys
from backend.mcp.client import mcp_manager

# Force the key (simulation)
# os.environ["VT_APIKEY"] = "dummy" 
# OR check if it's missing to reproduce the error

async def main():
    print("Testing MCP Connection...")
    try:
        async with mcp_manager.get_session("gti") as session:
            print("Session established!")
            print("Listing tools...")
            result = await session.list_tools()
            print(f"Tools found: {[t.name for t in result.tools]}")
            
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR:\n{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
