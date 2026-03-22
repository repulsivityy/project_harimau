import asyncio
import asyncpg
import os

async def main():
    db_url = "postgresql://harimau:harimau@127.0.0.1:5432/harimau?host=/cloudsql/virustotal-lab:asia-southeast1:harimau-db"
    try:
        # We can't easily connect to Cloud SQL from local script without proxy, but the backend is running WITH the proxy.
        print("Skipping direct local connection test as we are outside the cluster.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
