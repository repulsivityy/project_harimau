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

## 🚀 Deployment (GCP)
1.  **Prerequisites**: `gcloud` CLI installed and authenticated.
2.  **Configuration**:
    ```bash
    # Export your GTI API Key (will be securely saved to Secret Manager)
    export GTI_API_KEY="your_actual_key_here"
    ```
3.  **Run Script**:
    ```bash
    ./deploy.sh [backend|frontend|all]
    ```
    *   **Default**: Deploys both.
    *   **Selective API**: `./deploy.sh backend`
    *   **Selective UI**: `./deploy.sh frontend`
    This script will:
    *   Enable necessary GCP APIs (Cloud Run, Secret Manager, Vertex AI).
    *   Create/Update the `harimau-gti-api-key` secret.
    *   Build and Deploy Backend & Frontend services.

4.  **Verify Deployment**:
    ```bash
    curl -X POST "https://harimau-backend-<YOUR_PROJECT_ID>.asia-southeast1.run.app/investigate" \
         -H "Content-Type: application/json" \
         -d '{"ioc": "1.1.1.1"}'
    ```

## 📊 Status
- **Phase 1 (Infrastructure)**: ✅ Complete
- **Phase 2 (The Brain)**: ✅ Complete
- **Phase 3 (The Interface)**: ✅ Complete
- **Phase 3.5 (Hybrid Triage)**: ✅ Complete
- **Phase 4 (Specialist Agents)**: 🚧 In Progress

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
