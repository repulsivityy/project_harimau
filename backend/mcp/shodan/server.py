import os
import shodan

from mcp.server.fastmcp import FastMCP

server = FastMCP("Shodan MCP server", dependencies=["shodan"])


def get_shodan_client() -> shodan.Shodan:
    api_key = os.getenv("SHODAN_API_KEY")
    if not api_key:
        raise ValueError("SHODAN_API_KEY environment variable is required")
    return shodan.Shodan(api_key)


# Load tools
from .tools import *


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
