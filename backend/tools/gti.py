import aiohttp
import asyncio
import os
import certifi
import ssl
from backend.utils.logger import get_logger

logger = get_logger("tool_gti_direct")

BASE_URL = "https://www.virustotal.com/api/v3"

async def _fetch_relationship_objects(session: aiohttp.ClientSession, url: str, headers: dict, ssl_context: ssl.SSLContext) -> list:
    """Fetches full objects for a specific relationship."""
    try:
        # Use limit=10 to manage token usage while getting enough context
        # The relationship endpoint returns a list of full objects
        async with session.get(f"{url}?limit=10", headers=headers, ssl=ssl_context) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("data", [])
            return []
    except Exception as e:
        logger.error("gti_rel_fetch_failed", url=url, error=str(e))
        return []

async def _enrich_with_relationships(base_response: dict, session: aiohttp.ClientSession, headers: dict, ssl_context: ssl.SSLContext) -> dict:
    """
    Takes a base response with descriptor-only relationships and enriches them 
    by fetching full objects in parallel.
    """
    if not base_response or "data" not in base_response:
        return base_response

    relationships = base_response["data"].get("relationships", {})
    if not relationships:
        return base_response

    # Identify active relationships (those that returned descriptors)
    tasks = []
    rel_names = []

    for rel_name, rel_data in relationships.items():
        # Check if there are items to fetch
        if rel_data.get("data") and len(rel_data["data"]) > 0:
            # Construct relationship endpoint
            # links.related contains the URL to fetch full objects
            related_url = rel_data.get("links", {}).get("related")
            if related_url:
                rel_names.append(rel_name)
                tasks.append(_fetch_relationship_objects(session, related_url, headers, ssl_context))

    if not tasks:
        return base_response

    # Execute parallel fetch
    logger.info("gti_parallel_enrichment_start", count=len(tasks))
    results = await asyncio.gather(*tasks)

    # Merge results back into base_response
    for rel_name, full_objects in zip(rel_names, results):
        if full_objects:
            # Replace descriptors with full objects
            base_response["data"]["relationships"][rel_name]["data"] = full_objects
            
    logger.info("gti_parallel_enrichment_complete", enriched=len(tasks))
    return base_response

def _scrub_heavy_fields(data: any) -> any:
    """Recursively removes heavy fields (like last_analysis_results) to save tokens/bandwidth."""
    if isinstance(data, dict):
        # Delete the specific key if it exists
        if "last_analysis_results" in data:
            del data["last_analysis_results"]
        
        for key, value in data.items():
            _scrub_heavy_fields(value)
            
    elif isinstance(data, list):
        for item in data:
            _scrub_heavy_fields(item)
            
    return data

async def _make_request(endpoint: str, relationships: list[str] = None) -> dict:
    """Helper for async GTI requests with smart relationship enrichment."""
    api_key = os.getenv("GTI_API_KEY")
    if not api_key:
        logger.error("gti_missing_api_key")
        return {}

    headers = {
        "x-apikey": api_key,
        "Accept": "application/json",
        "x-tool": "project_harimau"
    }
    
    url = f"{BASE_URL}/{endpoint}"
    
    # 1. Discovery: Request with relationships param to get descriptors/counts
    if relationships:
        rel_string = ",".join(relationships)
        url += f"?relationships={rel_string}"
    
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    try:
        async with aiohttp.ClientSession() as session:
            # Fetch Base Report
            async with session.get(url, headers=headers, ssl=ssl_context) as response:
                if response.status == 200:
                    base_data = await response.json()
                    
                    # 2. Enrichment: If we asked for relationships, fetch full objects
                    if relationships:
                        base_data = await _enrich_with_relationships(base_data, session, headers, ssl_context)
                    
                    # 3. Optimization: Scrub heavy fields to save tokens/memory
                    _scrub_heavy_fields(base_data)
                        
                    return base_data
                    
                elif response.status == 404:
                    logger.warning("gti_not_found", url=url)
                    return {}
                else:
                    logger.error("gti_api_error", status=response.status, url=url)
                    return {}
                    
    except Exception as e:
        logger.error("gti_request_failed", error=str(e))
        return {}

async def get_ip_report(ip: str, relationships: list[str] = None) -> dict:
    return await _make_request(f"ip_addresses/{ip}", relationships)

async def get_domain_report(domain: str, relationships: list[str] = None) -> dict:
    return await _make_request(f"domains/{domain}", relationships)

async def get_file_report(file_hash: str, relationships: list[str] = None) -> dict:
    return await _make_request(f"files/{file_hash}", relationships)

async def get_url_report(url: str, relationships: list[str] = None) -> dict:
    import base64
    # URL ID encoding: base64 without padding
    try:
        url_id = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
        return await _make_request(f"urls/{url_id}", relationships)
    except Exception as e:
        logger.error("gti_url_encoding_failed", error=str(e))
        return {}
