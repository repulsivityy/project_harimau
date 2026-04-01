FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and graphing libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for caching
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy Backend Code (includes MCP servers in backend/mcp)
COPY backend /app/backend

# Set PYTHONPATH to include the current directory so imports work
ENV PYTHONPATH=/app

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Command to run the FastMCP / FastAPI server
# We will use uvicorn to run the FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
