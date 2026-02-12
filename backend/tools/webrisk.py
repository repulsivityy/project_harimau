import os
import aiohttp
import asyncio
from google.cloud import secretmanager
from backend.utils.logger import get_logger

logger = get_logger("tool_webrisk")

def get_webrisk_api_key() -> str:
    """
    Retrieves the WebRisk API Key.
    Priority:
    1. Environment Variable (Injected by Cloud Run)
    2. Secret Manager (Fallback/Local)
    """
    # 1. Check Env
    api_key = os.getenv("WEBRISK_API_KEY")
    if api_key:
        return api_key

    # 2. Check Secret Manager
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("webrisk_no_project_id_for_secret_lookup")
        return ""

    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project_id}/secrets/harimau-webrisk-api-key/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        api_key = response.payload.data.decode("UTF-8")
        logger.info("webrisk_secret_retrieved_from_gsm")
        return api_key
    except Exception as e:
        logger.error("webrisk_secret_fetch_failed", error=str(e))
        return ""

async def evaluate_uri(uri: str) -> dict:
    """
    Evaluates a URI using the Google Web Risk API.
    Docs: https://cloud.google.com/web-risk/docs/reference/rest/v1eap1/TopLevel/evaluateUri
    """
    api_key = get_webrisk_api_key()
    if not api_key:
        logger.error("webrisk_missing_api_key")
        return {"error": "Missing WebRisk API Key"}

    url = f"https://webrisk.googleapis.com/v1eap1:evaluateUri?key={api_key}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "uri": uri,
        "threatTypes": ["SOCIAL_ENGINEERING", "MALWARE", "UNWANTED_SOFTWARE"]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("webrisk_check_success", uri=uri)
                    return data
                else:
                    error_text = await response.text()
                    logger.error("webrisk_api_error", status=response.status, error=error_text)
                    return {"error": f"API Error {response.status}", "details": error_text}
    except Exception as e:
        logger.error("webrisk_request_failed", error=str(e))
        return {"error": f"Request failed: {str(e)}"}
