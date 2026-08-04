import os
import sys
import time
import subprocess
import httpx
from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Ghidra MCP Secure Gateway & Sample Loader")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key: str = Security(api_key_header)):
    expected_key = os.environ.get("GHIDRA_MCP_API_KEY")
    if not expected_key:
        # If no key configured in env, fail secure
        raise HTTPException(status_code=500, detail="Server misconfigured: GHIDRA_MCP_API_KEY not set.")
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid X-API-Key.")
    return api_key

# Background process reference for bridge-mcp-ghidra
bridge_process = None
BRIDGE_PORT = 8081
BRIDGE_URL = f"http://127.0.0.1:{BRIDGE_PORT}"

class DownloadSampleRequest(BaseModel):
    file_hash: str
    source: str = "vt"  # 'vt' or 'gti'

@app.on_event("startup")
async def startup_event():
    global bridge_process
    print("Starting background bridge-mcp-ghidra...")
    env = os.environ.copy()
    env["GHIDRA_MCP_REQUIRE_PROGRAM_SELECTORS"] = "1"
    
    cmd = [
        "uv", "run", "--directory", "/opt/ghidra-mcp",
        "bridge-mcp-ghidra",
        "--transport", "streamable-http",
        "--mcp-host", "127.0.0.1",
        "--mcp-port", str(BRIDGE_PORT)
    ]
    bridge_process = subprocess.Popen(cmd, env=env)
    print(f"bridge-mcp-ghidra started with PID {bridge_process.pid} on port {BRIDGE_PORT}")

@app.on_event("shutdown")
def shutdown_event():
    global bridge_process
    if bridge_process:
        print("Terminating bridge-mcp-ghidra...")
        bridge_process.terminate()

@app.post("/sample/download", dependencies=[Depends(get_api_key)])
async def download_sample(payload: DownloadSampleRequest):
    """
    Downloads a binary sample by hash from VirusTotal or GTI into /tmp/{file_hash}.
    """
    file_hash = payload.file_hash.strip().lower()
    target_path = os.path.join("/tmp", file_hash)
    
    if os.path.exists(target_path):
        return {"status": "already_exists", "path": target_path}

    async with httpx.AsyncClient(timeout=60.0) as client:
        if payload.source.lower() == "vt":
            vt_key = os.environ.get("VT_API_KEY")
            if not vt_key:
                raise HTTPException(status_code=500, detail="VT_API_KEY environment variable not set.")
            url = f"https://www.virustotal.com/api/v3/files/{file_hash}/download"
            headers = {"x-apikey": vt_key}
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"VT download failed: {resp.text}")
            content = resp.content
        elif payload.source.lower() == "gti":
            gti_key = os.environ.get("GTI_API_KEY")
            if not gti_key:
                raise HTTPException(status_code=500, detail="GTI_API_KEY environment variable not set.")
            # Adjust to GTI file download URL scheme if different
            url = f"https://www.virustotal.com/api/v3/files/{file_hash}/download"
            headers = {"x-apikey": gti_key}
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"GTI download failed: {resp.text}")
            content = resp.content
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported source '{payload.source}'")

    with open(target_path, "wb") as f:
        f.write(content)

    return {"status": "success", "path": target_path, "size": len(content)}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], dependencies=[Depends(get_api_key)])
async def proxy_mcp(request: Request, path: str):
    """
    Proxies all MCP streamable HTTP requests to the local bridge-mcp-ghidra instance.
    """
    url = f"{BRIDGE_URL}/{path}"
    async with httpx.AsyncClient(timeout=300.0) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers)
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ghidra MCP bridge is starting or unreachable.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
