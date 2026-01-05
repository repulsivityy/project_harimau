from mcp.server.fastmcp import FastMCP
import uvicorn

server = FastMCP("test")
print("Attributes:", dir(server))

# Check specific candidates
if hasattr(server, "_fastapi_app"):
    print("Found _fastapi_app")
if hasattr(server, "app"):
    print("Found app")
if hasattr(server, "create_application"):
    print("Found create_application")
