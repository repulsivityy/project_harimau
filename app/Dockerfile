FROM python:3.11-slim

WORKDIR /app

# Install dependencies (curl for healthcheck if needed, graphviz for charts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Copy and install frontend dependencies
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy Frontend Code
COPY app /app/frontend

# Copy utils/models if we decide to share code in future
# COPY backend/models /app/backend/models 

# Expose Streamlit port
EXPOSE 8501

# Streamlit-specific environment variables
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Run Command
CMD ["streamlit", "run", "frontend/main.py"]
