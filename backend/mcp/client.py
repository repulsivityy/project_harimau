import json
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from backend.utils.logger import get_logger

logger = get_logger("mcp_manager")

class MCPClientManager:
    """
    Manages connections to MCP servers based on a registry file.
    Supports 'stdio' (local subprocess) and 'sse' (remote - roadmap) transports.
    """
    def __init__(self, registry_path: str = "backend/mcp_registry.json"):
        self.registry_path = registry_path
        self._registry = self._load_registry()
        
    def _load_registry(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            logger.warning(f"MCP Registry not found at {self.registry_path}")
            return {}
        try:
            with open(self.registry_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error("failed_to_load_mcp_registry", error=str(e))
            return {}

    @asynccontextmanager
    async def get_session(self, server_name: str):
        """
        Context manager that yields a connected ClientSession for the requested server.
        """
        config = self._registry.get(server_name)
        if not config:
            raise ValueError(f"MCP Server '{server_name}' not found in registry.")

        transport_type = config.get("transport")

        if transport_type == "stdio":
            # Prepare subprocess parameters
            # Note: We need to ensure credentials are passed if they are in env
            env = os.environ.copy()
            # If config has specific env vars, add them (optional feature)
            
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=env
            )
            
            logger.info("connecting_mcp_stdio", server=server_name)
            
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
                    
        elif transport_type == "sse":
            # Roadmap feature
            raise NotImplementedError("SSE transport not yet implemented.")
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")

# Global singleton or dependency injection pattern can be used
mcp_manager = MCPClientManager()
