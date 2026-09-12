import aiohttp
import asyncio
import os
import certifi
import ssl
from backend.utils.logger import get_logger

logger = get_logger("tool_gti_direct")

BASE_URL = "https://www.virustotal.com/api/v3"

def _outcome(status: str, *, error: str | None = None, http_status: int | None = None) -> dict:
    """Small, JSON-safe result contract shared by direct GTI callers.

    Empty relationship lists are valid intelligence (``no_data``); transport,
    API and parsing failures are not.  Keep this metadata alongside the
    existing payload shape so older callers can continue reading ``data``.
    """
    result = {"status": status, "source": "gti"}
    if error:
        result["error"] = error
    if http_status is not None:
        result["http_status"] = http_status
    return result


async def _fetch_relationship_objects(session: aiohttp.ClientSession, url: str, headers: dict, ssl_context: ssl.SSLContext) -> tuple[list, dict]:
    """Fetch full objects and explicitly distinguish no data from failure."""
    try:
        # Use limit=10 to manage token usage while getting enough context
        # The relationship endpoint returns a list of full objects
        async with session.get(f"{url}?limit=10", headers=headers, ssl=ssl_context) as response:
            if response.status == 200:
                data = await response.json()
                objects = data.get("data", [])
                return objects, _outcome("succeeded" if objects else "no_data", http_status=200)
            error = f"GTI relationship request returned HTTP {response.status}"
            logger.warning("gti_rel_fetch_unsuccessful", url=url, status=response.status)
            return [], _outcome("failed", error=error, http_status=response.status)
    except Exception as e:
        logger.error("gti_rel_fetch_failed", url=url, error=str(e))
        return [], _outcome("failed", error=str(e))

async def _enrich_with_relationships(
    base_response: dict,
    session: aiohttp.ClientSession,
    headers: dict,
    ssl_context: ssl.SSLContext,
    requested_relationships: list[str],
) -> dict:
    """
    Takes a base response with descriptor-only relationships and enriches them 
    by fetching full objects in parallel.
    """
    if not base_response or "data" not in base_response:
        return base_response

    relationships = base_response["data"].get("relationships")
    if not isinstance(relationships, dict):
        base_response["data"]["_relationship_outcomes"] = {
            rel_name: _outcome("failed", error="GTI response omitted relationship descriptors")
            for rel_name in requested_relationships
        }
        return base_response

    # Identify active relationships (those that returned descriptors). A
    # descriptor list is actionable only when it includes a related link; an
    # omitted/malformed descriptor cannot be reinterpreted as no data.
    tasks = []
    rel_names = []
    enrichment_outcomes = {}
    for rel_name in requested_relationships:
        rel_data = relationships.get(rel_name)
        if not isinstance(rel_data, dict) or "data" not in rel_data:
            enrichment_outcomes[rel_name] = _outcome("failed", error="GTI response omitted relationship descriptor data")
            continue
        descriptors = rel_data.get("data")
        if not isinstance(descriptors, list):
            enrichment_outcomes[rel_name] = _outcome("failed", error="GTI relationship descriptor data was malformed")
            continue
        if not descriptors:
            enrichment_outcomes[rel_name] = _outcome("no_data")
            continue
        related_url = (rel_data.get("links") or {}).get("related")
        if not isinstance(related_url, str) or not related_url:
            enrichment_outcomes[rel_name] = _outcome("failed", error="GTI relationship descriptors lacked a related link")
            continue
        rel_names.append(rel_name)
        tasks.append(_fetch_relationship_objects(session, related_url, headers, ssl_context))

    if not tasks:
        base_response["data"]["_relationship_outcomes"] = enrichment_outcomes
        return base_response

    # Execute parallel fetch
    logger.info("gti_parallel_enrichment_start", count=len(tasks))
    results = await asyncio.gather(*tasks)

    # Merge results back into base_response
    for rel_name, (full_objects, outcome) in zip(rel_names, results):
        enrichment_outcomes[rel_name] = outcome
        if full_objects:
            # Replace descriptors with full objects
            base_response["data"]["relationships"][rel_name]["data"] = full_objects
    base_response["data"]["_relationship_outcomes"] = enrichment_outcomes
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
        return {"error": "GTI_API_KEY is not configured", "_outcome": _outcome("failed", error="GTI_API_KEY is not configured")}

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
        timeout = aiohttp.ClientTimeout(total=15.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Fetch Base Report
            async with session.get(url, headers=headers, ssl=ssl_context) as response:
                if response.status == 200:
                    base_data = await response.json()
                    if not isinstance(base_data, dict) or not isinstance(base_data.get("data"), dict):
                        error = "GTI response did not contain a valid root data object"
                        logger.error("gti_malformed_root_response", url=url)
                        return {"error": error, "_outcome": _outcome("failed", error=error, http_status=200)}
                    # Keep the successful root fetch explicit too. Older
                    # callers ignore this sibling field and continue using
                    # ``data`` unchanged.
                    base_data["_outcome"] = _outcome("succeeded", http_status=200)
                    
                    # 2. Enrichment: If we asked for relationships, fetch full objects
                    if relationships:
                        base_data = await _enrich_with_relationships(
                            base_data, session, headers, ssl_context, relationships
                        )
                    
                    # 3. Optimization: Scrub heavy fields to save tokens/memory
                    _scrub_heavy_fields(base_data)
                        
                    return base_data
                    
                elif response.status == 404:
                    logger.warning("gti_not_found", url=url)
                    return {"data": None, "_outcome": _outcome("no_data", http_status=404)}
                else:
                    logger.error("gti_api_error", status=response.status, url=url)
                    error = f"GTI request returned HTTP {response.status}"
                    return {"error": error, "_outcome": _outcome("failed", error=error, http_status=response.status)}
                    
    except Exception as e:
        logger.error("gti_request_failed", error=str(e))
        return {"error": str(e), "_outcome": _outcome("failed", error=str(e))}

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
        return {"error": str(e), "_outcome": _outcome("failed", error=str(e))}
