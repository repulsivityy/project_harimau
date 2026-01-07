from mcp.server.fastmcp import FastMCP
server = FastMCP("test")
app = server.sse_app()
print(f"Routes: {app.routes}")
for route in app.routes:
    print(f"Path: {route.path}, Name: {route.name}")
