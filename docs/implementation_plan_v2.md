# Implementation Checklist: Project Harimau (Modular Rebuild)

This document tracks the iterative evolution of the Harimau platform, organized by architectural Pillars and capability Milestones.

---

## Pillar 1: Infrastructure & Deployment
> **Focus**: Repository scaffolding, containerization, and cloud orchestration.

### Milestone 1: Local Environment & Core Scaffold ✅
*   [x] **Repo Setup**: Clear `old_archive`, setup `app/` (Frontend) and `backend/` (API).
*   [x] **Scaffold**: Create `app/` (Frontend) and `backend/` (Backend) directories.
*   [x] **Logging**: Implement `backend/utils/logger.py` for Structured JSON Logging.
*   [x] **Local Dev**: Create `docker-compose.yml` for FULL stack (Frontend + Backend + Database).

**Challenges & Learnings**
*   **Architecture Decision**: Prioritized a **Modular Monolith** (Embedded MCP) over Microservices.
    *   *Reasoning*: Reduces cost (1 container), eliminates network latency (`stdio`), and simplifies atomic deployments.

### Milestone 2: Cloud Run Deployment ✅
*   [x] **Deploy Scripts**: Create `deploy.sh` and `terraform/` for Cloud Run.
*   [x] **Deploy to Cloud Run**: Verified successful GCP deployment.
*   [x] **Selective Deployment**: Updated `deploy.sh` to allow deploying only backend or frontend to save time.
*   [x] **Docker Optimization**: Created `Dockerfile` for Monolith build (Backend + Embedded MCP).

---

## Pillar 2: Core Orchestration (LangGraph)
> **Focus**: State management, tool registries, and the central LangGraph workflow.

### Milestone 1: State Definition & Node Framework ✅
*   [x] **State Definition**: Define `AgentState` (Nodes, Edges, History).
*   [x] **Orchestrator**: Build the LangGraph workflow (Start -> Triage -> End).

### Milestone 2: MCP Registry & Tool Discovery ✅
*   [x] **MCP Registry**: Implement `MCPClientManager` using Registry Pattern.
    - [x] MVP: `mcp_registry.json` mapping tools to `stdio` commands.
*   [x] **MCP Setup**: Ported GTI MCP server code to `backend/mcp/`.

**Challenges & Learnings**
*   **Import Paths**: Code from external repos (e.g., `gti-mcp`) usually assumes it is the root package. When embedding it in a sub-module, imports must be converted to relative paths.
*   **Subprocess Environment**: The `python` command in a subprocess may not resolve to the parent environment. Always use `sys.executable` to guarantee the subprocess uses the active interpreter.

---

## Pillar 3: Agents & Intelligence Layer
> **Focus**: Triage logic, specialist agent capabilities, and cognitive reasoning loops.

### Milestone 1: Hybrid Triage Logic ✅
*   [x] **Step 1: Input Identification**: Regex/Heuristics for IOC type (hash/ip/domain/url).
*   [x] **Step 2: Fast Facts Extraction**: Synchronous enrichment of `threat_severity` and `verdict`.
*   [x] **Step 3: Forced Tool Loop**: Guaranteed at least one relationship fetch per investigation to counter LLM tool-skipping.
*   [x] **Step 4: Triage Summary**: Automated generation of initial verdict and key associations.

**Challenges & Learnings**
*   **Agent Robustness**: LLMs will skip tool calls if they think they "know" enough. Implemented a "Forced Tool Loop" to guarantee graph data population.
*   **API Parsing**: Discovered GTI `get_relationships` returns a `dict` (not list) for single entities. Patched `triage.py` to handle both types.

### Milestone 2: Specialist Agent Suite (Malware & Infra) ✅
*   [x] **Malware Specialist**: Deep dive into dropped files, C2 communications, and behavioral patterns.
*   [x] **Infrastructure Specialist**: Map passive DNS, hosting providers, and pivoting points.
*   [x] **Specialist Gate**: Implemented logic to route to valid specialists based on Triage subtasks.
*   [x] **Deterministic Graphing**: Moved graph population into tool wrappers to eliminate LLM hallucinations.
*   [x] **Iterative Report Accumulation**: Specialists now read previous reports to update findings instead of resetting.

---

## Pillar 4: Investigation Workflow & Execution Engine
> **Focus**: Orchestration of complex hunts, iterative loops, and performance scaling.

### Milestone 1: Lead Hunter Logic & Iterations ✅
*   [x] **Lead Threat Hunter**: Created synthesis agent to review specialist reports and find gaps.
*   [x] **Iterative Workflow**: Implemented 3-loop iteration logic (Triage -> Specialists -> Lead Hunter -> Specialists...).
*   [x] **Gap Analysis**: Automated discovery of "uninvestigated nodes" in the NetworkX cache to drive next steps.

### Milestone 2: Performance & Token Optimization ✅
*   [x] **Sub-3s Triage**: Parallel `aiohttp` enrichment for immediate frontend feedback.
*   [x] **Dual-Layer Data Model**: Store rich metadata (150+ fields) but send minified summaries (<10 fields) to LLM.
*   [x] **Results**: Token usage reduced from 200K-2M → <30K (-90%+) per investigation.

### Milestone 3: Background Processing & Parallel Scaling ✅
*   [x] **Async Processing**: GET/POST separation to prevent Cloud Run HTTP timeouts (8min investigations).
*   [x] **Parallel Specialists**: Enabled Malware and Infra agents to run simultaneously.
*   [x] **Graph Reducer**: Implemented custom reducer to deep-merge parallel findings into the state.
*   [x] **CPU Optimization**: Deployed with `--no-cpu-throttling` to ensure background tasks complete post-request.

### Milestone 4: Flow & Robustness Refactoring ⏳
*   [ ] **Fix Parallel State Race Condition**: Refactor `subtasks` reducer in `state.py` (currently overwriting state due to parallel execution) by merging via task ID or moving status tracking solely to the orchestration nodes.
*   [ ] **Consolidate Planning Roles**: Refactor workflow so Triage strictly outputs context/risk assessment, leaving all task planning to the Lead Hunter (e.g., Triage -> Lead Hunter Plan -> Specialists -> Lead Hunter Synthesize).
*   [ ] **Strict Target Schemas**: Replace regex 'safety net' parsing in Specialists by enforcing strict JSON schemas for targets in the planner.
*   [ ] **Extract Inner Tool Loops**: Refactor specialist nodes (`infrastructure.py`, `malware.py`) to use Langgraph's native `ToolNode` and conditional edges instead of internal python `while/for` loops, improving checkpointing visibility and preventing thread blocking.
*   [ ] **Remove Duplicate Graph Expansion**: Remove post-LLM relationship expansion logic in specialists, relying solely on MCP tool wrappers to safely modify the graph cache during the natural reasoning loop.
*   [ ] **Strict Structured Output**: Replace string parsing (`.replace("```json")`) with `with_structured_output()` to guarantee schema adherence and eliminate parsing fallbacks.
*   [ ] **Optimize NetworkX MultiDiGraph Merges**: Ensure deterministic edge keys when using `merge_graphs` (or switch to `DiGraph` if identical parallel edges are unnecessary) to prevent exponential edge duplication during parallel state merges.

---

## Pillar 5: Persistence & State Management
> **Focus**: Database integration, state checkpointing, and long-term storage.

### Milestone 1: Cloud SQL & Checkpointing ✅
*   [x] **Relational Persistence**: Replaced `JOBS` dict with Cloud SQL (Postgres).
*   [x] **LangGraph Checkpointing**: Integrated `AsyncPostgresSaver` to persist graph snapshots.
*   [x] **Auth Proxy**: Configured unix socket injection for secure Cloud Run ↔ SQL connectivity.

### Milestone 2: Shodan Enrichment ✅
*   [x] **Shodan MCP Server**: Built FastMCP server for IP/DNS exposure data.
*   [x] **Infrastructure Wiring**: Integrated JARM, SSL/TLS, and service exposure into Infra Agent analysis.

### Milestone 3: Graph Persistence (Zero-Ops Fix) ✅
*   [x] **Schema Migration**: Added `investigation_graph JSONB` column to `investigations` table; `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ensures idempotent rollout to existing Cloud SQL instances.
*   [x] **Persist NetworkX Graph**: `final_state["investigation_graph"]` (serialised via `nx.node_link_data()`) included in `save_job()`; `COALESCE` in the upsert prevents intermediate status updates from overwriting a completed graph.
*   [x] **Update Graph Endpoint**: `/api/investigations/{job_id}/graph` now calls `format_graph_from_cache()` when the stored graph is present; falls back to `format_investigation_graph()` for running jobs and legacy records.
*   [x] **New `format_graph_from_cache()`**: Added to `graph_formatter.py` — reads raw GTI attributes directly from `InvestigationCache` (resolving nested paths like `gti_assessment.verdict.value`) and produces richer tooltips, isMalicious flags, and typed colours.
*   [ ] **Retire `graph_formatter.py` reconstruction path**: Remove `format_investigation_graph()` and the `rich_intel`-based fallback once all records have migrated and the new path is validated in production.

**Why**: The NetworkX graph built by agents during investigation is richer than `rich_intel.relationships` but is currently discarded at job completion. Storing it in the existing JSONB column requires no new infrastructure and unlocks full edge metadata, typed relationships, and more accurate visualization.

---

## Pillar 6: User Interface & Experience
> **Focus**: Visual representations of threat data and agent transparency.

### Milestone 1: Streamlit MVP [LEGACY] ✅
*   [x] **FastAPI Client**: Wrapper for talking to Backend.
*   [x] **Graph Rendering**: `streamlit-agraph` implementation.
*   [x] **Polling Logic**: Async status checking.

### Milestone 2: Next.js Migration & Real-time SSE ✅
*   [x] **Next.js Rebuild**: Migrated legacy Streamlit features to React-based frontend.
*   [x] **SSE Integration**: Replaced polling with Server-Sent Events for real-time agent thoughts.
*   [x] **Agent Transparency**: Added "🔍 Agent Transparency" expander for tool traces and reasoning.
*   [x] **Graph Polish**: Hierarchical clustering, rich tooltips (filename/score/verdict), and centering logic.
*   [x] **Physics Layout**: Integrated `d3-force` with ReactFlow — repulsion, spring edges, organic layout.
*   [x] **Custom Node Components**: Icons by entity type (domain, IP, hash, URL), malicious red-halo, hover tooltips.

### Milestone 3: Graph Interactivity & Correctness ⏳
> **Dependency**: Complete Pillar 5 M3 (graph persistence) first — the detail panel and richer tooltips require full entity attributes only available after the zero-ops fix.

**ReactFlow Integration Fixes** (correctness & performance):
*   [ ] **Fix simulation side-effects**: Move `simulation.on("tick")` and `simulationRef` assignment out of the `setNodes` updater — side effects in state updaters are an anti-pattern that causes duplicate simulations under React 19 StrictMode.
*   [ ] **Add `nodeOrigin={[0.5, 0.5]}`**: d3-force uses centre coordinates; ReactFlow defaults to top-left. This offset makes all circular nodes visually misaligned.
*   [ ] **RAF throttle on tick**: Wrap `setNodes` tick callback in `requestAnimationFrame` (skip if frame already pending) to cap React re-renders at 60fps.
*   [ ] **Node drag pinning**: Implement `onNodeDragStop` to set `fx`/`fy` on the d3 sim node so dragged nodes stay put.
*   [ ] **Cancel RAF on unmount**: Add `cancelAnimationFrame` to the `useEffect` cleanup alongside `simulation.stop()`.

**UX Features** (post zero-ops fix):
*   [ ] **Node Selection + Detail Panel**: `onNodeClick` handler that opens a side panel showing full entity attributes from the persisted graph (threat score, vendor detections, relationships, verdict).
*   [ ] **fitView & Recenter Button**: Trigger `fitView` imperatively via `useReactFlow()` on graph load and via a visible "Recenter" button.
*   [ ] **Control Panel & Legend**: Small overlay panel explaining node colours/icons; toggle to hide clean nodes.

---

## Pillar 7: Configuration & Extensibility
> **Focus**: Global settings, environment tuning, and agent-to-agent protocols.

### Milestone 1: agents.yaml & A2A Integration ⏳
*   [x] **Configurable Depth**: Moved `max_iterations` to per-request setting.
*   [ ] **Central Config**: Port `agents.yaml` loader to standardize model names/temperatures.
*   [ ] **A2A Support**: Expose `/.well-known/agent.json` Agent Card.

---

## Pillar 8: External Integrations & Ecosystem
> **Focus**: External dependencies and decoupled subsystems.

### Milestone 1: Detection Agent Decoupling ✅
*   [x] **Decoupling**: Successfully moved Google SecOps / SIEM automation to the discrete `/detection_agent` repo.
*   [ ] **Webhook Support**: Finalize Lead Hunter "Push" notifications to the Detection Agent.

---

## Technical Reference (Appendix)
> Historical code snippets and setup commands for restoration.

<details>
<summary>Cloud SQL PostgreSQL Schema</summary>

```sql
CREATE TABLE IF NOT EXISTS investigations (
    job_id       TEXT PRIMARY KEY,
    status       VARCHAR(50)  NOT NULL DEFAULT 'running',
    ioc          VARCHAR(255) NOT NULL,
    ioc_type     VARCHAR(50),
    risk_level   VARCHAR(50),
    gti_score    INTEGER,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    final_report TEXT,
    metadata     JSONB
);
```
</details>

<details>
<summary>Cloud Run Background Task Deployment (CLI)</summary>

```bash
gcloud run deploy harimau-backend \
  --cpu="2" \
  --no-cpu-throttling \
  --add-cloudsql-instances PROJECT:REGION:INSTANCE
```
</details>
