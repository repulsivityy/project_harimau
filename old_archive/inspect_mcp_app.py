from mcp.server.fastmcp import FastMCP
server = FastMCP("test")
print(f"Type of sse_app: {type(server.sse_app)}")
print(f"Is callable? {callable(server.sse_app)}")
