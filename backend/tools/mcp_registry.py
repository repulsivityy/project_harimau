"""
MCP Registry - Tool Connection Management
Supports both Local STDIO (Phase 1) and Remote HTTP/SSE (Phase 2 Microservices)
"""

import os
import time
import json
from typing import Dict, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

class MCPRegistry:
    """
    Manages connections to MCP servers and routes tool calls.
    
    Modes:
    1. Local STDIO: Runs MCP server as a subprocess.
    2. Remote SSE: Connects to a deployed MCP server over SSE (Server-Sent Events).
    """
    
    def __init__(self):
        # Configuration
        self.servers = {
            "gti": {
                "mode": os.getenv("GTI_MCP_MODE", "stdio"),  # 'stdio' or 'http'
                # STDIO Config
                "command": os.getenv("GTI_MCP_COMMAND", "uv"),
                "args": ["--directory", os.getenv("GTI_MCP_PATH", "."), "run", "server.py"],
                "env": {
                    "GTI_API_KEY": os.getenv("GTI_API_KEY") or os.getenv("VIRUSTOTAL_API_KEY", "")
                },
                # HTTP/SSE Config
                # Should point to the base URL, e.g. https://service-url.run.app
                "url": os.getenv("GTI_MCP_URL", "http://localhost:8080"),
                
                "capabilities": [
                    "lookup_ioc",
                    "get_behavior_summary",
                    "get_file_report",
                    "get_ip_address_report", 
                    "get_domain_report",
                    "get_url_report",
                    "get_file_behavior_summary"
                ]
            }
        }

    async def call(self, server: str, tool: str, args: dict) -> dict:
        """Route tool call to appropriate MCP server."""
        if server not in self.servers:
            raise ValueError(f"Unknown server: {server}")
        
        config = self.servers[server]
        
        if tool not in config["capabilities"]:
            raise ValueError(f"Server {server} doesn't support tool {tool}")
        
        start_time = time.time()
        
        try:
            if config["mode"] == "stdio":
                result = await self._call_stdio(config, tool, args)
            elif config["mode"] == "http":
                result = await self._call_sse(config, tool, args)
            else:
                raise ValueError(f"Unknown mode: {config['mode']}")

            # Add metadata
            if isinstance(result, dict):
                result["_duration"] = time.time() - start_time
            
            return result
            
        except Exception as e:
            raise Exception(f"MCP Call Failed ({server}/{tool}): {str(e)}")

    from mcp.types import CallToolResult

    def _parse_result(self, mcp_result: CallToolResult) -> Any:
        """Helper to parse MCP result object."""
        text_content = []
        if hasattr(mcp_result, 'content'):
            for item in mcp_result.content:
                if hasattr(item, 'text'):
                    text_content.append(item.text)
        
        full_text = "\n".join(text_content)
        
        try:
            return json.loads(full_text)
        except (json.JSONDecodeError, ValueError):
            return {"raw_output": full_text}

    async def _call_stdio(self, config: dict, tool: str, args: dict) -> Any:
        """Execute tool via Local STDIO subprocess"""
        env = os.environ.copy()
        env.update(config.get("env", {}))
        
        server_params = StdioServerParameters(
            command=config["command"],
            args=config["args"],
            env=env
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_result = await session.call_tool(tool, args)
                return self._parse_result(mcp_result)

    async def _call_sse(self, config: dict, tool: str, args: dict) -> Any:
        """Execute tool via Remote SSE"""
        url = config['url']
        if not url.endswith("/sse"):
            url = f"{url}/sse"

        # Parse URL to extract host for proper headers
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host_header = parsed.netloc if parsed.netloc else "localhost:8080"

        # Add proper headers for SSE connection
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Host": host_header
        }

        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_result = await session.call_tool(tool, args)
                return self._parse_result(mcp_result)

# Global Instance
mcp_registry = MCPRegistry()
