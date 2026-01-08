# Implementation Checklist: Project Harimau V2

This document tracks the progress of the Harimau V2 rebuild.

## Phase 1: Infrastructure & Deployment
- [x] **Repo Setup**: Clear `old_archive`, setup `app/` (Frontend) and `backend/` (API).
- [x] **Scaffold**: Create `app/` (Frontend) and `backend/` (Backend) directories.
- [x] **Logging**: Implement `backend/utils/logger.py` for Structured JSON Logging.
- [x] **MCP Setup**: Copy GTI MCP server code to `backend/mcp/`.
- [x] **Docker**: Create `Dockerfile` (Monolith: Backend + Embedded MCP).
- [x] **Local Dev**: Create `docker-compose.yml` for FULL stack (Frontend + Backend + Database).
- [x] **Deploy Scripts**: Create `deploy.sh` and `terraform/` for Cloud Run.
- [x] **Verify**:
    - [-] Run `tests/test_infra.py` (Skipped: Hardened Env).
    - [-] Run `tests/test_mcp_load.py` (Skipped: Hardened Env).
    - [-] Run `tests/test_mcp_load.py` (Skipped: Hardened Env).
    - [x] **Deploy to Cloud Run** (GCP Verification: Success).
    - [ ] **Manual Verification**:
        - [ ] **Frontend Connectivity**: Click "Ping Backend" in Streamlit Sidebar to verify `BACKEND_URL` injection.
        - [ ] **Observability**: Check Cloud Logging for structured JSON logs from `health_check_called`.
- [x] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 1 Challenges & Learnings
*   **Architecture Decision**: Prioritized a **Modular Monolith** (Embedded MCP) over Microservices.
    *   *Reasoning*: Reduces cost (1 container), eliminates network latency (`stdio`), and simplifies atomic deployments. To redploy as microservices in the future phases / roadmap. 

## Phase 2: The Brain (LangGraph)
- [ ] **State Definition**: Define `AgentState` (Nodes, Edges, History).
- [ ] **MCP Registry**: Implement `MCPClientManager` using Registry Pattern.
    - [ ] MVP: `mcp_registry.json` mapping tools to `stdio` commands.
    - [ ] Roadmap: Support `sse` for future Serverless Function tools.
- [ ] **Config Engine**: Implement `agents.yaml` loader.
- [ ] **Nodes**:
    - [ ] `Triage Agent` (Gemini Flash)
    - [ ] `Malware Specialist` (Gemini Pro)
    - [ ] `Infrastructure Specialist` (Gemini Pro)
    - [ ] `Librarian` (Async Schema Cleaner)
- [ ] **Orchestrator**: Build the LangGraph workflow with Recursion Depth checks.
- [ ] **Verify**:
    - [ ] Run `pytest tests/unit/test_agents.py` (Mocked LLM inputs).
    - [ ] Run `pytest tests/integration/test_workflow.py` (Dry-run full graph).
- [ ] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 2 Challenges & Learnings
*   *Pending implementation...*

## Phase 3: The Interface (Streamlit)
- [ ] **API Client**: Implement wrapper to talk to Backend API.
- [ ] **Polling Logic**: Implement async status checking.
- [ ] **UI Components**:
    - [ ] Chat Interface
    - [ ] Graph Visualization (`streamlit-agraph`)
    - [ ] "Librarian Approval" Widget.
- [ ] **Verify**:
    - [ ] Run `pytest tests/api/test_endpoints.py` (Test FastAPI routes).
    - [ ] Manual Check: Streamlit UI loads and connects to local backend.
- [ ] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 3 Challenges & Learnings
*   *Pending implementation...*

## Phase 4: Near-Term Roadmap (Post-MVP)
- [ ] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.
- [ ] **Microservices Split**: *If* scaling requires it, extract the MCP server into a dedicated Cloud Run service (Sidecar).
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Crash Recovery**: Implement LangGraph Postgres Checkpointing to resume jobs after Cloud Run restarts.
