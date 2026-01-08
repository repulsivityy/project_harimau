import os
import asyncio
import pytest
from redis import asyncio as aioredis
from dotenv import load_dotenv

# Load env to get host/port
load_dotenv()

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = os.getenv("FALKORDB_PORT", "6379")

@pytest.mark.asyncio
async def test_falkordb_connection():
    """
    Smoke test to verify we can connect to FalkorDB (Redis).
    This doesn't test Graph logic, just connectivity.
    """
    print(f"Connecting to FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}...")
    try:
        redis_client = aioredis.Redis(host=FALKORDB_HOST, port=int(FALKORDB_PORT))
        response = await redis_client.ping()
        await redis_client.close()
        assert response is True
        print("✅ FalkorDB Connection Successful")
    except Exception as e:
        pytest.fail(f"❌ Failed to connect to FalkorDB: {e}")

if __name__ == "__main__":
    # If run directly as a script
    asyncio.run(test_falkordb_connection())
