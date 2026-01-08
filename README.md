# Project Harimau (V2)

**Cloud-Native AI Threat Hunter**

Project Harimau is an automated threat investigation platform. It uses a graph-based multi-agent system (LangGraph) to mimic the workflow of a SOC team.

## Architecture V2
*   **Frontend**: Streamlit (Cloud Run Service).
*   **Backend**: FastAPI + LangGraph (Cloud Run Service).
*   **MCP**: Embedded GTI Server (stdio).
*   **Brain**: Gemini 3.0 Pro / Flash.
*   **Memory**: FalkorDB (GraphRAG).

## Features
*   **Modularity**: Add tools via `mcp_registry.json` and agents via `agents.yaml`.
*   **Reliability**: Async worker architecture handles long investigations without timeouts.
*   **CostSafe™**: Built-in recursion depth limits.
*   **Self-Refining**: "Librarian" agent proposes schema improvements for human approval.

## Quick Start (Local)

1.  **Clone & Env:**
    ```bash
    cp .env.example .env
    # Add GTI_API_KEY
    ```

2.  **Run Infrastructure:**
    ```bash
    docker-compose up -d falkordb
    ```

3.  **Run Backend (API):**
    ```bash
    cd backend && uvicorn app.main:app --reload
    ```

4.  **Run Frontend (UI):**
    ```bash
    cd app && streamlit run main.py
    ```

## Documentation
*   [Product Requirements (PRD)](docs/PRD.md)
*   [Architecture Proposal](docs/architecture.md)
*   [Implementation Plan](docs/implementation_plan.md)
