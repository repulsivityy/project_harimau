"""
MCP Registry - Tool Connection Management
Supports both Local STDIO (Phase 1) and Remote HTTP (Phase 2)
"""

import os
import asyncio
import httpx
import time
from typing import Dict, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPRegistry:
    """
    Manages connections to MCP servers and routes tool calls.
    
    Modes:
    1. Local STDIO (Phase 1): Runs MCP server as a subprocess (e.g., `uv run server.py`).
    2. Remote HTTP (Phase 2): Connects to a deployed MCP server over HTTP.
    """
    
    def __init__(self):
        # Configuration - Can be loaded from Env Vars or Config File
        self.servers = {
            "gti": {
                "mode": os.getenv("GTI_MCP_MODE", "stdio"),  # 'stdio' or 'http'
                # STDIO Config
                "command": os.getenv("GTI_MCP_COMMAND", "uv"),
                "args": ["--directory", os.getenv("GTI_MCP_PATH", "."), "run", "server.py"],
                "env": {
                    "vt_apikey": os.getenv("GTI_API_KEY") or os.getenv("VIRUSTOTAL_API_KEY", "")
                },
                # HTTP Config
                "url": os.getenv("GTI_MCP_URL", "http://localhost:3001"),
                
                "capabilities": [
                    "lookup_ioc",
                    "get_behavior_summary",
                    "get_file_report",
                    "get_ip_address_report", 
                    "get_domain_report",
                    "get_url_report",
                    "get_file_behavior_summary"
                ]
            },
            "shodan": {
                "mode": os.getenv("SHODAN_MCP_MODE", "stdio"),
                "command": os.getenv("SHODAN_MCP_COMMAND", "uv"),
                "args": ["--directory", os.getenv("SHODAN_MCP_PATH", "."), "run", "server.py"],
                "env": {
                    "SHODAN_API_KEY": os.getenv("SHODAN_API_KEY", "")
                },
                "url": os.getenv("SHODAN_MCP_URL", "http://localhost:3002"),
                "capabilities": ["ip_lookup", "search"]
            }
        }
        
        # HTTP client for Remote mode
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def call(self, server: str, tool: str, args: dict) -> dict:
        """
        Route tool call to appropriate MCP server.
        """
        # Validate server
        if server not in self.servers:
            raise ValueError(f"Unknown server: {server}")
        
        config = self.servers[server]
        
        # Validate capability
        if tool not in config["capabilities"]:
            raise ValueError(f"Server {server} doesn't support tool {tool}")
        
        start_time = time.time()
        
        try:
            # Dispatch based on mode
            if config["mode"] == "stdio":
                result = await self._call_stdio(config, tool, args)
            elif config["mode"] == "http":
                result = await self._call_http(config, tool, args)
            else:
                raise ValueError(f"Unknown mode: {config['mode']}")

            # Add metadata
            if isinstance(result, dict):
                result["_duration"] = time.time() - start_time
            
            return result
            
        except Exception as e:
            # Wrap error
            raise Exception(f"MCP Call Failed ({server}/{tool}): {str(e)}")

    async def _call_stdio(self, config: dict, tool: str, args: dict) -> Any:
        """Execute tool via Local STDIO subprocess"""
        
        # Prepare environment
        env = os.environ.copy()
        env.update(config.get("env", {}))
        
        # Prepare params
        server_params = StdioServerParameters(
            command=config["command"],
            args=config["args"],
            env=env
        )
        
        # Connect and Call
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call tool
                mcp_result = await session.call_tool(tool, args)
                
                # Parse result (extract text content)
                # MCP returns types.CallToolResult with content list
                text_content = []
                if hasattr(mcp_result, 'content'):
                    for item in mcp_result.content:
                        if hasattr(item, 'text'):
                            text_content.append(item.text)
                
                full_text = "\n".join(text_content)
                
                # Try to parse as JSON, else return raw text
                try:
                    import json
                    return json.loads(full_text)
                except:
                    return {"raw_output": full_text}

    async def _call_http(self, config: dict, tool: str, args: dict) -> Any:
        """Execute tool via Remote HTTP"""
        url = f"{config['url']}/tools/{tool}"
        
        response = await self.http_client.post(
            url,
            json={"arguments": args}
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.http_client.aclose()

# Global Instance
mcp_registry = MCPRegistry()
