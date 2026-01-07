from mcp.server.fastmcp import FastMCP
server = FastMCP("test")
try:
    app = server.sse_app()
    print(f"Return type: {type(app)}")
except Exception as e:
    print(f"Error calling: {e}")
