FROM ubuntu:24.04

# Prevent interactive timezone/debconf prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="/root/.local/bin:${PATH}"

# 1. Install system prerequisites (Java 21 LTS, Maven 3.9+, Python 3, tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jdk-headless \
    maven \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    unzip \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Install astral 'uv' package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Download and extract Ghidra 12.1.2 PUBLIC
WORKDIR /opt
RUN curl -L -o ghidra_12.1.2_PUBLIC.zip \
    "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.2_build/ghidra_12.1.2_PUBLIC_20241217.zip" \
    && unzip -q ghidra_12.1.2_PUBLIC.zip \
    && mv ghidra_12.1.2_PUBLIC ghidra \
    && rm -f ghidra_12.1.2_PUBLIC.zip

# 4. Clone bethington/ghidra-mcp repository
RUN git clone https://github.com/bethington/ghidra-mcp.git /opt/ghidra-mcp

# 5. Build and deploy the Ghidra MCP extension into headless Ghidra
WORKDIR /opt/ghidra-mcp
RUN uv venv /opt/ghidra-mcp/.venv && \
    uv pip install --no-cache fastapi uvicorn httpx pydantic && \
    uv run python -m tools.setup ensure-prereqs --ghidra-path /opt/ghidra && \
    uv run python -m tools.setup build && \
    uv run python -m tools.setup deploy --ghidra-path /opt/ghidra

# 6. Copy the entrypoint gateway & sample loader script
WORKDIR /app
COPY entrypoint.py /app/entrypoint.py

# Expose standard Cloud Run port
EXPOSE 8080

# 7. Start the secure entrypoint server (which manages bridge-mcp-ghidra in background)
CMD ["/opt/ghidra-mcp/.venv/bin/python", "/app/entrypoint.py"]
