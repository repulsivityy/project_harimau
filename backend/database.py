import os
import uuid
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import asyncpg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as PostgresSaver

# Global pool
_pool = None

def _convert_sqlalchemy_url_to_dsn(db_url: str) -> str:
    """
    Convert a SQLAlchemy-style database URL to an asyncpg-compatible DSN.
    
    SQLAlchemy format: postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/instance
    asyncpg DSN format: postgresql://user:pass@/dbname?host=/cloudsql/instance
    
    Also handles standard hostnames without socket paths.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    
    # Remove the +asyncpg dialect suffix
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "")
    
    # Parse the URL
    parsed = urlparse(db_url)
    
    # For Cloud SQL socket connections, asyncpg can use the URL format directly
    # after removing the +asyncpg dialect. No DSN conversion needed.
    # asyncpg supports: postgresql://user:pass@/dbname?host=/cloudsql/instance
    
    return db_url

async def get_db_pool():
    global _pool
    if _pool is None:
        db_url = os.getenv("DB_URL")
        if not db_url:
            raise ValueError("DB_URL environment variable is required")
        
        # Convert SQLAlchemy URL format to asyncpg-compatible format
        asyncpg_url = _convert_sqlalchemy_url_to_dsn(db_url)
        _pool = await asyncpg.create_pool(asyncpg_url)
    return _pool

async def init_db():
    """Initialize database tables"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Create Jobs Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS investigation_jobs (
                id TEXT PRIMARY KEY,
                ioc TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result JSONB
            );
        """)

class JobManager:
    """Manages investigation jobs persistence"""
    
    @staticmethod
    async def create_job(ioc: str, status: str = 'queued') -> str:
        pool = await get_db_pool()
        job_id = f"inv-{uuid.uuid4().hex[:8]}"
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO investigation_jobs (id, ioc, status) VALUES ($1, $2, $3)",
                job_id, ioc, status
            )
        return job_id

    @staticmethod
    async def update_job(job_id: str, status: str, result: Optional[dict] = None):
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            query = "UPDATE investigation_jobs SET status = $1, updated_at = NOW()"
            params = [status]
            if result:
                query += ", result = $2"
                params.append(result)
            query += " WHERE id = $" + str(len(params) + 1)
            params.append(job_id)
            await conn.execute(query, *params)

    @staticmethod
    async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM investigation_jobs WHERE id = $1", job_id)
            if row:
                res = dict(row)
                # Parse result JSON if exists
                # AsyncPG handles JSONB deserialization automatically
                # Convert timestamps to str
                res['created_at'] = str(res['created_at'])
                res['updated_at'] = str(res['updated_at'])
                return res
        return None
