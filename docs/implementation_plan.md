# Implementation Checklist: Project Harimau V2

This document tracks the progress of the Harimau V2 rebuild.

## Phase 1: Infrastructure & Core
- [x] **Repo Setup**: Clear `old_archive`, setup `app/` (Frontend) and `backend/` (API).
- [ ] **Logging**: Implement `backend/utils/logger.py` for Structured JSON Logging.
- [ ] **MCP Setup**: Copy GTI MCP server code to `backend/mcp/`.
- [ ] **Docker**: Create `Dockerfile` (Monolith: Backend + Embedded MCP).
- [ ] **Graph DB**: Create `docker-compose.yml` for local FalkorDB.
- [ ] **Verify**:
    - [ ] Run `tests/test_infra.py` (Checks DB connection).
    - [ ] Run `tests/test_mcp_load.py` (Checks Embedded MCP startup).
- [ ] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 1 Challenges & Learnings
*   *Pending implementation...*

## Phase 2: The Brain (LangGraph)
- [ ] **State Definition**: Define `AgentState` (Nodes, Edges, History).
- [ ] **MCP Client**: Implement `MCPClientManager` to run the embedded server.
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

## Phase 4: Deployment
- [ ] **Script**: `deploy.sh` (gcloud commands).
- [ ] **Terraform**: `terraform/` module for Cloud Run & Secrets.
- [ ] **CI/CD**: Cloud Build config (Optional).
- [ ] **Verify**:
    - [ ] Run `./deploy.sh` in a test GCP project.
    - [ ] Run `tests/smoke_test_prod.py` against deployed URL.
- [ ] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 4 Challenges & Learnings
*   *Pending implementation...*

## Phase 5: Near-Term Roadmap (Post-MVP)
- [ ] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Crash Recovery**: Implement LangGraph Postgres Checkpointing to resume jobs after Cloud Run restarts.
