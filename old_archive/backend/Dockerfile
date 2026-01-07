FROM python:3.12-slim

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend backend/
# Use environment variables

# Configure Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8080

# Run FastAPI
CMD ["uvicorn", "backend.main:app"]
