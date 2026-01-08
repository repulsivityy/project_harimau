FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# gcc/python3-dev might be needed for some packages, keeping it slim for now
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install graphing libraries for artifact generation
RUN apt-get update && apt-get install -y graphviz

# Copy dependencies first for caching
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy MCP Server code (Embedded)
COPY backend/mcp /app/mcp

# Copy Backend Code
COPY backend /app/backend

# Set PYTHONPATH to include the current directory so imports work
ENV PYTHONPATH=/app

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Command to run the FastMCP / FastAPI server
# We will use uvicorn to run the FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
