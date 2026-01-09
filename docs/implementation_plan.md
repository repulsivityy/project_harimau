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
- [x] **State Definition**: Define `AgentState` (Nodes, Edges, History).
- [x] **MCP Registry**: Implement `MCPClientManager` using Registry Pattern.
    - [x] MVP: `mcp_registry.json` mapping tools to `stdio` commands.
    - [ ] Roadmap: Support `sse` for future Serverless Function tools.
- [x] **Config Engine**: Implement `agents.yaml` loader (Basic).
- [x] **Nodes (MVP)**:
    - [x] `Triage Agent` (Gemini Flash + Vertex AI).
- [x] **Orchestrator**: Build the LangGraph workflow (Start -> Triage -> End).
- [x] **API Integration**: Expose `POST /investigate` endpoint.
- [x] **Verify**:
    - [x] **Cloud Verification**: Run `deploy.sh` and test endpoint (`curl -X POST https://.../investigate -d '{"ioc":"1.1.1.1"}'`).
    - [ ] Run `pytest tests/unit/test_agents.py` (Mocked LLM inputs).
    - [ ] Run `pytest tests/integration/test_workflow.py` (Dry-run full graph).
- [x] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 2 Challenges & Learnings
*   **MCP Integration**:
    *   **Import Paths**: Code from external repos (e.g., `gti-mcp`) usually assumes it is the root package. When embedding it in a sub-module (`backend.mcp.gti`), imports must be converted to relative paths (e.g., `from .tools import *`).
    *   **Subprocess Environment**: The `python` command in a subprocess may not resolve to the same environment as the parent process (especially in venvs or containers). Always use `sys.executable` to guarantee the subprocess uses the active interpreter.

## Phase 3: The Interface (Streamlit)
- [x] **API Client**: Implement wrapper to talk to Backend API.
- [x] **Polling Logic**: Implement async status checking.
- [x] **UI Components**:
    - [x] Chat Interface
    - [x] Graph Visualization (`streamlit-agraph`)
    - [x] "Librarian Approval" Widget.
- [x] **Verify**:
    - [x] Run `pytest tests/api/test_endpoints.py` (Test FastAPI routes).
    - [x] Manual Check: Streamlit UI loads and connects to local backend.
- [x] **Documentation**: Update PRD/Architecture/Readme with any changes.

### Phase 3 Challenges & Learnings
*   **UI/UX**: `streamlit-agraph` is great for simple graphs but can be laggy with large datasets. Ensuring the graph only renders when nodes exist was critical to avoid errors.


### Phase 3.5: Hybrid Triage & Specialist Agents
**Goal**: Implement a "Hybrid" Triage process that combines deterministic data extraction with agentic reasoning.

#### [COMPLETED] [Hybrid Triage Agent](backend/agents/triage.py)
*   **Step 1: Input & Identification** [COMPLETED]
    *   Input: `hash | domain | ip | url`.
    *   Logic: Use Regex/Heuristics to strictly identify the IOC type.
*   **Step 2: Fast Facts Extraction (Python)** [COMPLETED]
    *   Task: Fetch the "Base Report" immediately.
    *   Extraction: Manually parse `threat_severity`, `last_analysis_stats` (malicious count), and `verdict` (mapped from fallback if needed).
    *   Output: Populate `state["metadata"]` for immediate frontend display.
*   **Step 3: Agentic Reasoning (Tool-Use Loop)** [COMPLETED]
    *   Input: "Fast Facts" + "Base Report" JSON + User Prompt.
    *   Tools: Bind dynamic relationship tools (e.g., `get_entities_related_to_an_ip`, `get_entities_related_to_a_domain`).
    *   Instructions: "Use tools to validate the verdict and find campaign/actor associations."
*   **Step 4: Reasoning & Graph Population** [IN-PROGRESS]
    *   The Agent iterates:
        - [x] UI: Display Rich Intel (Verdict, Score, Desc)
        - [x] Robustness: Forced Tool Execution Loop (to guarantee graph data)
        - [x] Debugging: Added `/api/debug/investigation/{job_id}` endpoint
        *   "I see a high severity IP. Let me check its communicating files."
        *   "I see a file hash. Let me check for parent domains."
    *   State Update: Every tool result enriches the `state["metadata"]["rich_intel"]` and implicitly builds the graph.
*   **Step 5: Triage Report** [IN-PROGRESS]
    *   Agent generates a `summary` explaining the verdict and key associations.
*   **Step 6: Specialist Handoff** [IN-PROGRESS]
    *   Agent generates `subtasks` to route to `malware_specialist` or `infrastructure_specialist` for deep dive.

#### [NEW] [Malware Specialist](backend/agents/malware.py)
*   Receives file hash or suspicious artifact.
*   Tools: `get_file_report`, `get_entities_related_to_a_file`.
*   Task: Deep dive into behavior, capabilities, and associated campaigns.

#### [NEW] [Infrastructure Specialist](backend/agents/infrastructure.py)
*   Receives IP/Domain.
*   Tools: `get_ip_report`, `get_domain_report`, Passive DNS resolution.
*   Task: Map infrastructure, find pivoting points.

### Phase 3.5 Challenges & Learnings
*   **GTI MCP Server**: Needed to go from a full triage agent to a hybrid triage agent.
*   **Selective Deployment**: Updated `deploy.sh` to allow deploying only backend or frontend to save time. 
*   **Graph Population**: The MCP Tool `get_entities_related_to_...` required `descriptors_only=True` to return valid lists for the graph. Without it, the data was empty. [TO VALIDATE AGAIN]
*   **Agent Loop Logic**: Ensuring the agent loop doesn't silently fail if it exhausts turns without a final answer was critical. Added fallback to `messages` history. 

## Phase 4: Near-Term Roadmap (Post-MVP)
- [ ] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.
- [ ] **Microservices Split**: *If* scaling requires it, extract the MCP server into a dedicated Cloud Run service (Sidecar).
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Crash Recovery**: Implement LangGraph Postgres Checkpointing to resume jobs after Cloud Run restarts.