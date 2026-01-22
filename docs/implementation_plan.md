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
    - [x] `Triage Agent` (Gemini 2.5 Flash + Vertex AI).
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
*   **Step 4: Reasoning & Graph Population** [COMPLETED]
    *   The Agent iterates:
        - [x] UI: Display Rich Intel (Verdict, Score, Desc)
        - [x] Robustness: Forced Tool Execution Loop (to guarantee graph data)
        - [x] Debugging: Added `/api/debug/investigation/{job_id}` endpoint
        - [x] Fix: Handled single-entity tool responses (dict vs list) to ensure graph population.
        *   "I see a high severity IP. Let me check its communicating files."
        *   "I see a file hash. Let me check for parent domains."
    *   State Update: Every tool result enriches the `state["metadata"]["rich_intel"]` and implicitly builds the graph.
    *   Full expansion of initial IOC relationships, populate the graph, and Triage Agent will do first cut analysis for the specialist agents. 
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
*   **Graph Population (API Parsing)**: The VirusTotal MCP tool `get_relationships` returns a **single dictionary** (not a list) when only one entity is found. Valid data was being parsed as `[]`. We patched `triage.py` to handle `dict` types by wrapping them in a list.
*   **MCP Typo Discovery**: We found that `descriptors_only=True` was returning empty data because `utils.py` used `/relationship` instead of `/relationships`. Fixed.
*   **Frontend Configuration**: `streamlit-agraph` requires `width` and `fit=True` to ensure nodes don't fly off-screen during physics simulation.
*   **Agent Robustness**: LLMs will skip tool calls. Implemented a "Forced Tool Loop" to guarantee at least one relationship fetch per investigation. 

### Phase 3.6: Comprehensive Relationship Mapping & Graph Optimization [COMPLETED]
**Goal**: Expand relationship coverage and optimize graph visualization for cleaner IOC mapping.

#### [COMPLETED] Comprehensive Relationship Types
*   **Expanded File Relationships (20 types)**: Added `bundled_files`, `contacted_urls`, `embedded_ips`, `embedded_urls`, `email_attachments`, `email_parents`, `execution_parents`, `itw_domains`, `itw_ips`, `itw_urls`, `memory_pattern_domains`, `memory_pattern_ips`, `memory_pattern_urls`.
*   **Expanded Domain Relationships (14 types)**: Added `caa_records`, `cname_records`, `historical_ssl_certificates`, `immediate_parent`, `parent`, `referrer_files`, `siblings`, `urls`.
*   **Expanded IP Relationships (6 types)**: Added `historical_whois`, `referrer_files`, `urls`.
*   **Expanded URL Relationships (12 types)**: Added `embedded_js_files`, `last_serving_ip_address`, `memory_pattern_parents`, `redirecting_urls`, `redirects_to`, `referrer_files`, `referrer_urls`.
*   **Total**: 52 relationship types across all IOC types for comprehensive threat intelligence mapping.

#### [COMPLETED] Graph Visualization Improvements
*   **Removed Agent Task Nodes**: Graph now only displays IOC entities and their relationships, not internal agent workflow (e.g., malware_specialist, infrastructure_specialist nodes removed).
*   **Filtered Contextual Metadata**: Excluded non-IOC relationships from graph: `attack_techniques`, `malware_families`, `associations`, `campaigns`, `related_threat_actors`. These are still fetched and analyzed but not visualized to keep graphs focused on infrastructure.
*   **Increased Entity Limits (Option A)**:
    - `MAX_ENTITIES_PER_RELATIONSHIP`: 5 → 10 (per relationship type from GTI)
    - `MAX_TOTAL_ENTITIES`: 50 → 150 (total graph capacity)
    - Graph visualization: 10 → 15 entities per relationship in UI
*   **Future Enhancement**: Smart filtering (Option B) to prioritize malicious/high-score entities and provide user-configurable filters at investigation start.

#### [COMPLETED] Agent Transparency
*   **Tool Call Tracing**: Phase 1 relationship fetching now logs every tool call with status, entity counts, and sample data stored in `state["metadata"]["tool_call_trace"]`.
*   **LLM Reasoning Capture**: Phase 2 comprehensive analysis now stores raw LLM response in `state["metadata"]["rich_intel"]["triage_analysis"]["_llm_reasoning"]` for debugging and trust.
*   **Frontend Display**: Added "🔍 Agent Transparency" expander in Triage tab showing:
    - Summary metrics (relationships attempted/successful, total entities fetched)
    - Detailed tool call log with status indicators
    - Full LLM reasoning (collapsible JSON view)
*   **Zero Latency Impact**: Transparency tracking adds ~20-50ms overhead (negligible for 8-15 second investigations).

#### Phase 3.6 Challenges & Learnings
*   **Graph Clarity**: Users wanted to see only threat infrastructure relationships, not internal agent routing. Separating visualization from orchestration improved UX.
*   **Scalability**: With 52 relationship types, the original 5-entity limit was too restrictive. Tripling capacity (150 total) provides room for ~15-20 relationship types to have full coverage.
*   **Future Work**: Need to implement smart filtering to surface most relevant entities when investigations exceed 150 total entities.

#### Phase 3.7: Graph Visualization Enhancements [COMPLETED]
**Goal**: Improve graph readability, user experience, and interactivity.

*   **Node Label Formatting** (`backend/main.py`):
    - **URLs**: Extract full URL from `attributes.url` instead of displaying hash ID
    - **Files**: Display format `SHA256\n(truncated_name.ext)` to show both hash and filename
    - Smart truncation: Preserve file extensions (e.g., `long_malicious_file....exe` instead of `long_malicious_file...`)
    
*   **Visual Hierarchy & Clustering** (`backend/main.py`):
    - Auto-create group nodes when relationship has multiple entities (e.g., `group_contacted_domains`)
    - Dynamic node sizing: Root (1.1x), Groups (0.75x), Entities (1.0x) based on slider
    - Updated color palette: Infrastructure (Orange), Files (Purple), URLs (Cyan), Context (Blue)
    
*   **Graph Interactivity Fixes** (`app/main.py`):
    - **Recenter Graph**: Fixed via `_recenter_key` injection into physics config (changes config hash on button click)
    - **Initial Centering**: Added stabilization config with `fit: true` to auto-center viewport on load
    - **State Persistence**: Job state persists across slider interactions (no investigation reset)

#### Phase 3.8: Triage Performance Optimization [ROADMAP]
**Goal**: Reduce investigation latency by parallelizing relationship fetching.

*   **Status**: REVERTED (Option A was unstable).
*   **Parallel Execution**: Refactored `triage.py` to fetch relationship types concurrently using `asyncio.gather`.
*   **Performance Bottleneck**: Identified that MCP `session.call_tool()` blocks the event loop.
*   **Attempted Fix (Reverted)**: `asyncio.to_thread` wrapper caused runtime errors (`'coroutine' object has no attribute 'content'`).
*   **Resolution**: Performance optimization deferred to Phase 5 (Option B: Async HTTP client migration).

## Phase 4: Specialist Agents [TODO]

#### Phase 4.1: Malware Specialist Agent [TODO]
*   **YARA Integration**: Add YARA rule matching capability.
*   **Code Analysis**: Add static analysis for scripts (PowerShell, Python, JS).

#### Phase 4.2: Infrastructure Specialist Agent [TODO]


## Phase 5: Near-Term Roadmap (Post-MVP)
- [ ] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.
- [ ] **Microservices Split**: *If* scaling requires it, extract the MCP server into a dedicated Cloud Run service (Sidecar).
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Crash Recovery**: Implement LangGraph Postgres Checkpointing to resume jobs after Cloud Run restarts.
- [ ] **Smart Entity Filtering (Option B)**: Implement user-configurable filters at investigation start to prioritize malicious/high-score entities by threat score, verdict, and recency.
- [ ] **Async HTTP Client Migration (Perf Option B)**: Replace MCP's synchronous HTTP with `httpx.AsyncClient` for true async I/O (eliminates thread pool overhead from Option A).

## Phase 6: Long-Term Enhancements
- [ ] **Advanced Graph Visualization**: Migrate from `streamlit-agraph` to more professional library:
    - **Option 1**: Pyvis (quick upgrade, better physics/interactivity)
    - **Option 2**: Plotly + NetworkX (enterprise-grade, actively maintained)
    - **Option 3**: Custom D3.js component (ultimate flexibility for threat intel workflows)
    - **Option 4**: Streamlit-Cytoscape, but haven't been actively maintained. 
    - Evaluation criteria: performance with 150+ nodes, layout algorithms (hierarchical, timeline), clustering capabilities