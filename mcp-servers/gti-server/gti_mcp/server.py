# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Add lifespan support for startup/shutdown with strong typing
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

import logging
import os
import vt

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings

logging.basicConfig(level=logging.INFO)

# If True, creates a completely fresh transport for each request
# with no session tracking or state persistence between requests.
stateless = False
if os.getenv("STATELESS") == "1":
  stateless = True


def _vt_client_factory(unused_ctx) -> vt.Client:
  api_key = os.getenv("GTI_API_KEY")
  if not api_key:
    raise ValueError("GTI_API_KEY environment variable is required")
  return vt.Client(api_key.strip())

vt_client_factory = _vt_client_factory


@asynccontextmanager
async def vt_client(ctx: Context) -> AsyncIterator[vt.Client]:
  """Provides a vt.Client instance for the current request."""
  client = vt_client_factory(ctx)

  try:
    yield client
  finally:
    await client.close_async()

# Create a named server and specify dependencies for deployment and development
# Disable DNS rebinding protection for Cloud Run deployment
security_settings = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP(
    "Google Threat Intelligence MCP server",
    dependencies=["vt-py"],
    stateless_http=stateless,
    transport_security=security_settings)

# Load tools.
from gti_mcp.tools import *

# Run the server
def main():
  import sys
  transport = os.getenv("MCP_TRANSPORT", "stdio")
  if transport == "sse":
      import uvicorn
      # FastMCP exposes the internal ASGI app via sse_app()
      app = server.sse_app()
      logging.info("Starting GTI MCP Server (Standardized Env)")
      port = int(os.getenv("PORT", 8080))
      uvicorn.run(app, host="0.0.0.0", port=port)
  else:
      server.run(transport='stdio')


if __name__ == '__main__':
  main()
