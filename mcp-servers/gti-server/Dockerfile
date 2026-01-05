FROM python:3.12-slim

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install dependencies (gti-mcp package)
RUN pip install --no-cache-dir .

# Configuration for Cloud Run
ENV MCP_TRANSPORT=sse
ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8080
ENV PORT=8080

# Run the server
# Note: We run the module which invokes server.run()
# Our modified server.py checks MCP_TRANSPORT to enable SSE mode
CMD ["python", "-m", "gti_mcp.server"]
