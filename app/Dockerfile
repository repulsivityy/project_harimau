FROM python:3.11-slim

WORKDIR /app

# Install dependencies (curl for healthcheck if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install specific dependencies for Frontend
RUN pip install streamlit requests streamlit-agraph

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
