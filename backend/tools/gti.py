import aiohttp
import os
import certifi
import ssl
from backend.utils.logger import get_logger

logger = get_logger("tool_gti_direct")

BASE_URL = "https://www.virustotal.com/api/v3"

async def _make_request(endpoint: str, relationships: list[str] = None) -> dict:
    """Helper for async GTI requests."""
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
    if relationships:
        rel_string = ",".join(relationships)
        url += f"?relationships={rel_string}"
    
    # SSL Context for Mac cert quirks
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=ssl_context) as response:
                if response.status == 200:
                    return await response.json()
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
