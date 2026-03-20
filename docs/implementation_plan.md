# Implementation Checklist: Project Harimau

This document tracks the progress of the Harimau rebuild.

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
- [ ] **Config Engine**: `agents.yaml` loader scaffolded in `backend/utils/config.py` but not yet wired up — agent behaviors currently hardcoded per agent. To be completed in Phase 6 (see below).
- [x] **Nodes (MVP)**:
    - [x] `Triage Agent` (Gemini Flash + Vertex AI).
- [x] **Orchestrator**: Build the LangGraph workflow (Start -> Triage -> End).
- [x] **API Integration**: Expose `POST /api/investigate` endpoint.
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
*   **Step 5: Triage Report** [COMPLETED]
    *   Agent generates a `summary` explaining the verdict and key associations.
*   **Step 6: Specialist Handoff** [COMPLETED]
    *   Agent generates `subtasks` to route to `malware_specialist` or `infrastructure_specialist` for deep dive.

#### [COMPLETED] [Malware Specialist](backend/agents/malware.py)
*   **Behavior Analysis**: Deep dive into dropped files, C2 communications, and execution patterns
*   **Tools**: `get_file_report`, `get_entities_related_to_a_file`.
*   **Programmatic Reporting**: Generates structured Markdown reports outside the LLM context for 100% stability.
*   **Automatic Indicator Sync**: Discovered indicators (C2s, dropped files) are automatically pushed to both the NetworkX cache and LangGraph state for immediate frontend visibility.
*   **Source-Aware Graphing**: Links shared infrastructure (e.g., common C2 IPs) back to the specific malware hash that contacted them.

#### [COMPLETED] [Infrastructure Specialist](backend/agents/infrastructure.py)
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

#### Phase 3.7: Performance & UX Polish [COMPLETED]
- [x] **Sub-3s Triage**: Migrated to Direct API Bundle with parallel `aiohttp` enrichment.
- [x] **Graph Visibility**: Hierarchical clustering for high-volume nodes.
- [x] **State Persistence**: Fixed UI reset bug using `st.session_state`.
- [x] **Smart Labels**: Implemented filename truncation and attribute-first URL labeling.

#### Phase 3.8: Token Optimization [COMPLETED]
**Goal**: Reduce LLM token consumption for file IOC investigations from 200K-2M to <30K.

**Problem**: File IOC investigations were exceeding Gemini token limits and incurring high costs.

**Solution - Dual-Layer Data Model**:
- [x] **Reduced Relationships**: File IOCs now fetch 11 critical types instead of 20 (-45%):
  - `associations`, `malware_families`, `attack_techniques`
  - `contacted_domains`, `contacted_ips`
  - `dropped_files`, `embedded_domains`, `embedded_ips`
  - `execution_parents`, `itw_domains`, `itw_ips`
- [x] **Minimal Entity Storage**: Extract only essential fields for LLM analysis (9 fields: id, type, display_name, verdict, threat_score, malicious_count, file_type, reputation, name).
- [x] **Display Field Separation**: Store rich fields (url, meaningful_name, names, size, categories) for graph visualization separately.
- [x] **LLM Context Filtering**: `prepare_detailed_context_for_llm()` filters entities to LLM-relevant fields only.

**Results**:
- Token usage: 200K-2M → <30K (-90%+)
- Analysis depth: Maintained ✅
- Graph visualization: Enhanced with display fields ✅

#### Phase 3.8 Challenges & Learnings
*   **Storage vs Context**: Storage size doesn't matter for tokens - only what's sent to LLM matters.
*   **Separation of Concerns**: Store everything, send minimal summaries, query on-demand.
*   **Alpha Pattern**: Inspired by `ai_threathunter` project's approach of full fetch + minimal LLM context.

#### Phase 3.9: Visualization Enhancements & Bug Fixes [COMPLETED]
**Goal**: Fix graph visualization issues and improve tooltip quality.

**Enhancements**:
- [x] **Full URLs**: Display complete URL strings instead of truncated versions.
- [x] **File Names**: Show `meaningful_name` or first filename instead of truncated hash.
- [x] **Rich Tooltips**: Human-readable format showing:
  - Threat score (e.g., "Threat Score: 85")
  - Vendor detections (e.g., "42 vendors detected as malicious")
  - File metadata (filename, type, size in MB)
  - URL categories
  - Verdict
- [x] **URL Categories**: Added extraction and display for URL entities.
- [x] **Agent Reports**: Added individual agent reports in markdown for clarity and transparency.

**Bug Fixes (Jan 2026)**:
- [x] **UnboundLocalError**: Fixed variable shadowing in `triage.py` line 464 (`gti` → `gti_data`).
  - **Issue**: Local variable `gti = attrs.get("gti_assessment", {})` shadowed imported `gti` module.
  - **Impact**: 500 Internal Server Error in Cloud Run deployment.
  - **Fix**: Renamed local variable to `gti_data`.
- [x] **Empty Tooltips**: Added display fields to entity extraction (was showing `{}`).
- [x] **Tooltip Formatting**: Changed from JSON dump to human-readable multi-line text.

#### Phase 3.9 Challenges & Learnings
*   **Over-Optimization**: Initial token optimization removed fields needed for visualization.
*   **Dual-Purpose Data**: Entities now serve both LLM analysis and graph display by filtering at query time.
*   **User Experience**: Graph tooltips are critical for investigation - users need filenames, not hashes.

### Phase 4: Specialist Agents [COMPLETE]
- [x] **Routing Fix**: Strictly limited the orchestrator to valid specialists (`malware_specialist`).
- [x] **Malware Specialist Agent**: Deep dive into behavior, capabilities, and associated campaigns.
- [x] **Infrastructure Specialist**: Map infrastructure, find pivoting points.
- [x] **NetworkX Investigation Cache**
- [x] **Enhanced Visualization**: Mouseover tooltips, root node hashes, and centering logic.
  
**NetworkX Cache Benefits**:
- Full entity attributes cached in-memory per investigation
- LLM queries minimal fields (token-efficient)
- Specialists get full context without API re-fetch
- Future migration path: NetworkX (MVP) → FalkorDB (Production)

### Phase 4.1: Agent Stabilization & Production Hardening [COMPLETE]
*Deployment Revisions: 135-139 | Date: 2026-01-30*

**Critical Bug Fixes**:
- [x] **JSON Parsing Robustness**: Implemented dual-format parser to handle both `{...}` objects and `[{...}]` arrays from LLM
- [x] **MCP Tool Argument Mapping**: Fixed `ip` → `ip_address` parameter mismatch preventing IP analysis
- [x] **Empty Content Fallback**: Added robust message history traversal to capture final LLM response when loop exits early
- [x] **Target Discovery**: Implemented regex fallback in Infrastructure Agent for missing `entity_id` in subtasks
- [x] **Subtask Lifecycle**: Added status updates to mark completed specialist work

**Structural Improvements**:
- [x] **Code Alignment**: Unified Malware and Infrastructure agent patterns (removed Pydantic schemas causing deployment crashes)
- [x] **Error Visibility**: Enhanced error reporting from 500 to 2000 characters with structured output
- [x] **Agent Iterations**: Increased loop limit from 3 to 7 turns for comprehensive analysis
- [x] **Logic Cleanup**: Removed duplicate fallback code, restored missing imports

**Documentation**:
- [x] Created comprehensive debugging guide (`docs/agent_debugging_guide.md`)
- [x] Created implementation reference (`docs/agent_implementation.md`)
- [x] Created project changelog (`CHANGELOG.md`)
- [x] Created documentation index (`docs/README.md`)

**Technical Debt Resolved**:
- Pydantic BaseModel schemas removed (deployment-safe pattern)
- All MCP parameter names verified across layers
- Fallback logic standardized (not duplicated)
- Error handling three-layer approach implemented

**Impact**:
- Both specialist agents now reliably complete analyses
- Infrastructure Agent successfully processes IPs, domains, URLs
- Reduced "System Error" failures from ~40% to <5%
- Comprehensive troubleshooting documentation for future issues

## Phase 5: Iterative Investigation Workflow [COMPLETED]

### Phase 5.1: Specialist Agent Enhancements [COMPLETED]
**Goal**: Enable specialists to read triage context and expand the investigation graph.

**Completed Tasks**:
- [x] State Management Refactor
- [x] Specialist Gate Implementation
- [x] Malware Agent: Triage context integration + graph expansion
- [x] Infrastructure Agent: Triage context integration + graph expansion
- [x] Bug fixes: Empty content fallback, JSON extraction, scope errors
- [x] Local verification scripts

**Impact**: Graph now grows from ~50 nodes (triage) to ~150 nodes (after specialists).

---

### Phase 5.2: Lead Threat Hunter Agent [COMPLETED]
**Goal**: Orchestrate iterative investigations (max 3 iterations).
**Completion Date**: Jan 2026

**See**: `docs/agent_implementation.md` for full technical specification.

**Completed Tasks**:
- [x] Created `backend/agents/lead_hunter_synthesis.py` with LLM-based orchestration logic
- [x] Added `get_uninvestigated_nodes()` to InvestigationCache
- [x] Updated workflow: Added gate and lead hunter nodes, implemented iteration loop
- [x] Added `iteration` and `lead_hunter_report` to AgentState
- [x] Testing: Integration and end-to-end verification
- [x] Deployed and verified iteration behavior

**Lead Hunter Responsibilities**:
1. Review triage + specialist reports
2. Analyze graph to find uninvestigated entities
3. Prioritize high-value targets (malicious, attack-chain-relevant)
4. Create subtasks for next iteration
5. Generate holistic synthesis report with markdown and graphviz diagrams
6. Decide: continue (if iteration ≤ 3 and targets exist) or end

**Workflow**:
```
Iteration 0: Triage → Gate → [Malware, Infra] → Lead Hunter → Decision
Iteration 1: Gate → [Malware, Infra] → Lead Hunter → Decision
Iteration 3: Gate → [Malware, Infra] → Lead Hunter → END (max reached)
```

**Impact**:
- Investigations now run iteratively with dynamic task generation
- Lead Hunter synthesizes findings across all agents

---

### Phase 5.3: Production Fixes & Cloud Run Optimization [COMPLETED]
**Goal**: Fix critical production issues preventing investigations from completing.
**Completion Date**: Feb 2026

#### Async Background Processing Implementation
**Problem**: Investigations taking 8+ minutes exceeded Cloud Run HTTP connection timeout (60-300s), causing 503 errors in frontend.

**Solution**:
- [x] Modified `backend/main.py` POST /api/investigate to return immediately with job_id
- [x] Investigation runs via `asyncio.create_task` in background
- [x] Frontend polls GET /api/investigations/{job_id} every 10 seconds
- [x] Progress bar calculates based on elapsed time (~8.5 min average), caps at 95%

**Impact**:
- Zero connection timeout errors
- Investigations complete reliably end-to-end
- Improved user experience with real-time status updates

#### Parallel Specialist Execution Fixes
**Problem**: Malware and Infrastructure agents ran in parallel but data was being overwritten, timeline/tasks not displaying.

**Solutions**:
- [x] **Graph Reducer**: Added custom reducer to deep-merge parallel specialist findings in NetworkX cache
- [x] **Iteration Logic**: Fixed Lead Hunter condition from `>= max_iterations` to `> max_iterations` to allow synthesis at final iteration
- [x] **Subtask Preservation**: Subtasks now stored in `metadata["rich_intel"]["triage_analysis"]["subtasks"]` to survive Lead Hunter state clearing
- [x] **Backend Retrieval**: Backend extracts subtasks from metadata fallback when state array is empty

**Impact**:
- Frontend timeline and agent tasks now display correctly
- Parallel execution confirmed working
- No more missing investigation data

#### Malware Agent Enhancements
**Capabilities Added**:
- [x] **get_file_report** tool - Full static analysis report from GTI
- [x] **Vulnerabilities enrichment** - get_attribution now fetches CVEs and exploits
- [x] **Target limiting** - Added `max_analysis_targets = 5` (separate from `malware_iterations = 10`)

**Impact**:
- Richer threat intelligence with vulnerability context
- Investigations stay within API/token limits
- Controlled analysis depth without overwhelming system

**Total Deployments**: 20+ iterations to production in Feb 2026

**Phase 5 is complete - Product is production-ready as of Feb 2026**

**Current Workflow Implementation**:
```
graph TD
    Start([IOC Submitted]) --> Triage[Triage Agent]
    
    Triage -->|Extract Targets & Assign Tasks| SpecialistGate{Specialist Gate}
    
    subgraph IterationLoop [Investigation Cycle - Max 3 Loops]
        direction TB
        SpecialistGate -->|Parallel Execution| Malware[Malware Agent]
        SpecialistGate -->|Parallel Execution| Infra[Infrastructure Hunter]
    end
    Malware --> LeadReview[Lead Threat Hunter]
Infra --> LeadReview
    LeadReview -->|Analyze Reports & Gap Analysis| LoopCheck{Loop < 3?}
    LoopCheck -->|Yes: Issue Directives| SpecialistGate
    
    LoopCheck -->|No / Satisfied| Consolidation[Final Consolidation]
    LeadReview -->|Satisfied| Consolidation -->|Final Markdown + Diagrams + Report by Lead Hunter| End([Investigation Complete])
```



## Phase 6: Near-Term Roadmap (Post-MVP)

### Phase 6.1: Cloud SQL + LangGraph Checkpointing
**Goal**: Replace the ephemeral in-memory `JOBS` dict with Cloud SQL (PostgreSQL) and wire LangGraph `PostgresSaver` so investigations persist across Cloud Run restarts and can be retrieved at any time.

**Why**: Cloud Run scales to zero — any in-memory state is lost on restart. All investigation results, graph data, and mid-investigation state currently disappear on container restart. Cloud SQL is external to the container and persists indefinitely.

**Current state summary**:
- `JOBS = {}` dict defined at `backend/main.py` line 44 — all reads/writes go through this
- `app_graph` imported from `backend/graph/workflow.py` — compiled at line 72 with no checkpointer: `return workflow.compile()`
- `backend/requirements.txt` has no PostgreSQL or LangGraph checkpoint dependencies
- `terraform/main.tf` has Cloud Run services only — no Cloud SQL resources
- `docker-compose.yml` has FalkorDB (unused) and backend/frontend — no PostgreSQL service

---

#### Step 1: Add Dependencies
**File**: `backend/requirements.txt`

Add the following lines:
```
asyncpg
psycopg[binary]
langgraph-checkpoint-postgres
```

---

#### Step 2: Add PostgreSQL to `docker-compose.yml` (Local Dev)
**File**: `docker-compose.yml`

Add a `postgres` service so local development mirrors Cloud SQL:
```yaml
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: harimau
      POSTGRES_USER: harimau
      POSTGRES_PASSWORD: harimau
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

Add `postgres_data` to the `volumes` block at the bottom.

Add to the `backend` service:
- `depends_on: [postgres]`
- Environment variable: `DATABASE_URL=postgresql://harimau:harimau@postgres:5432/harimau`

Also remove or comment out the `falkordb` service and its `FALKORDB_HOST`/`FALKORDB_PORT` env vars from the backend — FalkorDB is Phase 7 and currently unused.

---

#### Step 3: Provision Cloud SQL via Terraform
**File**: `terraform/main.tf`

Add the following resources after the existing Cloud Run service definitions:

```hcl
# Enable Cloud SQL API
resource "google_project_service" "sqladmin_api" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

# Cloud SQL PostgreSQL instance
resource "google_sql_database_instance" "harimau_db" {
  name             = "harimau-db"
  database_version = "POSTGRES_15"
  region           = var.region
  depends_on       = [google_project_service.sqladmin_api]

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled = false  # No public IP — use Cloud SQL Auth Proxy
    }
  }

  deletion_protection = false  # Set true for production
}

resource "google_sql_database" "harimau" {
  name     = "harimau"
  instance = google_sql_database_instance.harimau_db.name
}

resource "google_sql_user" "harimau_user" {
  name     = "harimau"
  instance = google_sql_database_instance.harimau_db.name
  password = var.db_password  # Add variable "db_password" {} to the vars block
}

# Grant Cloud Run SA access to Cloud SQL
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

data "google_compute_default_service_account" "default" {}
```

Add `variable "db_password" {}` to the variables block.

---

#### Step 4: Store Connection String in Secret Manager
**Script** (run once manually or add to `deploy.sh`):

```bash
# Connection string format for Cloud SQL Auth Proxy
DB_URL="postgresql://harimau:YOUR_DB_PASSWORD@/harimau?host=/cloudsql/${PROJECT_ID}:asia-southeast1:harimau-db"
printf "$DB_URL" | gcloud secrets create harimau-db-url --data-file=-
gcloud secrets add-iam-policy-binding harimau-db-url \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

---

#### Step 5: Update `deploy.sh` for Backend Deploy
**File**: `deploy.sh`

In the backend `gcloud run deploy` command (currently around the `--set-secrets` line), add:
```bash
--set-secrets "...,DATABASE_URL=harimau-db-url:latest" \
--add-cloudsql-instances ${PROJECT_ID}:${REGION}:harimau-db \
```

Also add `sqladmin.googleapis.com` to the `gcloud services enable` line at the top of the script.

---

#### Step 6: Create DB Schema on Startup
**File**: `backend/main.py`

Add a `db_pool` global and schema creation to the `lifespan` context manager (currently lines 15–21):

```python
import asyncpg
import os

db_pool = None  # global connection pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    # Startup
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        db_pool = await asyncpg.create_pool(db_url)
        async with db_pool.acquire() as conn:
            await conn.execute("""
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
                CREATE INDEX IF NOT EXISTS idx_investigations_created
                    ON investigations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_investigations_status
                    ON investigations(status);
            """)
        logger.info("database_connected", status="pool_created")
    else:
        logger.warning("database_not_configured", fallback="in-memory JOBS dict")
    yield
    # Shutdown
    if db_pool:
        await db_pool.close()
```

**Important**: Keep `JOBS = {}` as a fallback for local dev without a database. Use `db_pool` when available, fall back to `JOBS` when not.

---

#### Step 7: Replace `JOBS` Dict Reads/Writes
**File**: `backend/main.py`

Add a helper to abstract DB vs in-memory:
```python
async def save_job(job_id: str, data: dict):
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO investigations (job_id, status, ioc, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (job_id) DO UPDATE
                SET status = $2, metadata = $4::jsonb, completed_at = NOW()
            """, job_id, data.get("status"), data.get("ioc"), json.dumps(data))
    else:
        JOBS[job_id] = data

async def get_job(job_id: str):
    if db_pool:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM investigations WHERE job_id = $1", job_id)
            return dict(row) if row else None
    else:
        return JOBS.get(job_id)
```

Replace all direct `JOBS[job_id] = ...` and `JOBS.get(job_id)` calls with `await save_job(...)` and `await get_job(...)`:

| Current (main.py) | Replace with |
|---|---|
| Line 58: `JOBS[job_id] = {...}` | `await save_job(job_id, {...})` |
| Line 206: `JOBS[job_id] = result` | `await save_job(job_id, result)` |
| Lines 221–222: `JOBS[job_id]["status"] = "failed"` | `await save_job(job_id, {"status": "failed", ...})` |
| Line 237: `JOBS.get(job_id)` | `await get_job(job_id)` |
| Line 263: `job_id not in JOBS` | `await get_job(job_id) is None` |

---

#### Step 8: Wire LangGraph `PostgresSaver`
**File**: `backend/graph/workflow.py`

Current line 72: `return workflow.compile()`

Change to accept an optional checkpointer:
```python
from langgraph.checkpoint.postgres import PostgresSaver

def create_graph(checkpointer=None):
    workflow = StateGraph(AgentState)
    # ... all existing node/edge definitions unchanged ...
    return workflow.compile(checkpointer=checkpointer)
```

**File**: `backend/main.py`

On startup (inside `lifespan`, after pool creation), create the graph with checkpointer:
```python
from langgraph.checkpoint.postgres import PostgresSaver

# Inside lifespan, after db_pool is created:
checkpointer = PostgresSaver(db_pool)
await checkpointer.setup()  # creates langgraph checkpoint tables
app_graph = create_graph(checkpointer=checkpointer)
```

Pass `thread_id` in every `graph.ainvoke()` call in `_run_investigation_background`:
```python
config = {"configurable": {"thread_id": job_id}}
result = await app_graph.ainvoke(inputs, config=config)
```

This means if Cloud Run restarts mid-investigation, the same `job_id` resumes from the last completed node.

---

#### Verification Checklist (before deploying to Cloud Run)
- [ ] `docker-compose up` starts `postgres` + `backend` without errors
- [ ] `POST /api/investigate` returns `job_id` and row appears in `investigations` table
- [ ] `GET /api/investigations/{job_id}` returns result after completion
- [ ] Kill backend mid-investigation (`docker-compose restart backend`), verify job resumes from last checkpoint
- [ ] `GET /api/investigations/{job_id}` still works after restart (reads from DB, not JOBS dict)
- [ ] Deploy to Cloud Run with `DATABASE_URL` secret and `--add-cloudsql-instances` — verify same behaviour

---

### Phase 6.2: Agent Configuration (`agents.yaml`)
**Goal**: Centralize agent tuning parameters into a config file, removing hardcoded constants from agent code.

**Why**: Currently, key operational parameters are scattered across individual agent files (e.g., `malware_iterations = 10` in `malware.py`, model names hardcoded per agent). As the agent count grows (OSINT, Detection, SOC agents planned), per-file management becomes unwieldy. Model selection (Flash vs Pro) and iteration limits are tuning concerns, not code concerns — changing them should not require a deployment.

**What goes in `agents.yaml` vs stays in code:**

| In `agents.yaml` | Stays in code |
|---|---|
| Model name per agent (flash vs pro) | System prompts (too long, no syntax support in YAML) |
| Iteration limits | Tool definitions |
| Max targets | LangGraph node logic |
| Temperature | Error handling |
| Feature flags (e.g., `detection_agent_enabled`) | |

**Tasks:**
- [ ] Define `backend/config/agents.yaml` schema with triage, malware, infrastructure, lead_hunter entries
- [ ] Update each agent to read model, iterations, max targets, and temperature from config via `load_agents_config()`
- [ ] Add `detection_agent_enabled` and `detection_agent_url` as config entries (alongside env var support)
- [ ] Validate config on startup with clear error messages for missing/invalid values
- [X] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.

- [ ] **A2A Integration**: Expose Harimau as an A2A-compatible agent:
    - Publish `/.well-known/agent.json` Agent Card
    - Add inbound A2A task endpoint (`POST /a2a/tasks/send`) to trigger investigations from external agents
    - Add optional outbound handoff to detection_agent on investigation completion
    - Controlled by `DETECTION_AGENT_ENABLED` + `DETECTION_AGENT_URL` env vars on the **backend Cloud Run service only** — the frontend is unaware of this integration
    - Toggle live without redeploying: `gcloud run services update harimau-backend --set-env-vars DETECTION_AGENT_ENABLED=true,DETECTION_AGENT_URL=https://...`
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Smart Entity Filtering**: Implement user-configurable filters at investigation start to prioritize malicious/high-score entities by threat score, verdict, and recency.
- [ ] **Enhance security**: Implement security measures
- [ ] **Ongoing Efforts**
    - [ ] Advanced prompting for autonomous decisions
    - [ ] Adaptive iteration limits
    - [ ] Hunt package generation (YARA/Sigma)
    - [X] Timeline reconstruction
    - [X] Tools - Webrisk
    - [ ] Tools - URLScan
    - [ ] Tools - Shodan
    - [ ] Tools - OpenCTI
    - [ ] Tools - Google SecOps

### Phase 6.3: Multi-User Support & Persistence

> **Status**: Planned for Phase 6 — design documented below
> **Current MVP**: Single-user, ephemeral architecture

#### Requirements

**1. User Authentication & Authorization**
- [ ] **Identity**: Implement user authentication via Google IAP/IAM
- [ ] **Job Ownership**: Associate each `job_id` with a `user_id`
- [ ] **Access Control**: Users can only stream/view their own investigations
  ```python
  # Future: Verify user owns this job before allowing SSE subscription
  if JOBS[job_id]["user_id"] != current_user_id:
      raise HTTPException(403, "Unauthorized")
  ```

**2. SSE Event Routing**
- [ ] **Per-User Isolation**: Events must only stream to authorized subscribers
  - Current: Broadcast to all subscribers of a `job_id` (works for single-user MVP)
  - Future: Verify user identity before adding to subscriber list

**3. Investigation Persistence (LangGraph Checkpointing)**
- [ ] **State Persistence**: Store investigation state across restarts
  - **Technology**: `langgraph.checkpoint.postgres.PostgresSaver` (Cloud SQL)
  - **Purpose**: Resume interrupted investigations, replay past investigations, support "expand this IOC" from old jobs
- [ ] **Implementation**:
  ```python
  from langgraph.checkpoint.postgres import PostgresSaver

  checkpointer = PostgresSaver(connection_string="postgresql://...")
  app_graph = workflow.compile(checkpointer=checkpointer)
  ```

**4. Job History & Retrieval**
- [ ] **Database Schema**: Replace in-memory `JOBS` dict with Cloud SQL (PostgreSQL)
  ```sql
  CREATE TABLE investigations (
      job_id UUID PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      status VARCHAR(50),
      ioc VARCHAR(255),
      created_at TIMESTAMP,
      completed_at TIMESTAMP,
      final_report TEXT,
      investigation_graph JSONB,
      metadata JSONB
  );

  CREATE INDEX idx_user_jobs ON investigations(user_id, created_at DESC);
  ```
- [ ] **Job Listing API**: `GET /api/investigations?user_id={user_id}&limit=50`
- [ ] **Job Retrieval**: `GET /api/investigations/{job_id}` (verify ownership)

**5. Event History Replay**
- [ ] Store SSE events in PostgreSQL on emission; replay to late subscribers on connection

#### Recommended Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| **User Auth** | Google IAP/IAM | GCP-native, enforced at Cloud Run level |
| **Database** | Cloud SQL (PostgreSQL) | Persistent, supports JSONB, LangGraph compatibility |
| **Checkpointing** | `langgraph.checkpoint.postgres.PostgresSaver` | Official LangGraph support |
| **Event Storage** | Same PostgreSQL (separate table) | Simple, consistent |
| **Session Management** | Redis (Cloud Memorystore) | Fast ephemeral data for active investigations |

#### Architecture

**Current (MVP - Single User)**:
```
┌─────────────┐
│  Browser    │──SSE──┐
└─────────────┘       │
                      ▼
┌─────────────────────────────────┐
│  FastAPI Backend                │
│  ┌───────────────────────────┐  │
│  │  In-Memory JOBS Dict      │  │
│  │  sse_manager._subscribers │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  LangGraph (No Checkpoint)│  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

**Future (Multi-User + Persistence)**:
```
┌─────────────┐
│  Browser    │──Auth Token──┐
│  (User A)   │──SSE─────────┼──┐
└─────────────┘              │  │
┌─────────────┐              │  │
│  Browser    │──SSE─────────┼──┤
│  (User B)   │              │  │
└─────────────┘              │  │
                             ▼  ▼
┌─────────────────────────────────────────┐
│  FastAPI Backend                        │
│  ┌───────────────────────────────────┐  │
│  │  Auth Middleware (verify user_id) │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  SSE Manager (user-aware routing) │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  LangGraph + PostgresSaver        │  │
│  └───────────────────────────────────┘  │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Cloud SQL (PostgreSQL)     │
│  ┌─────────────────────────┐│
│  │  investigations table   ││
│  │  event_history table    ││
│  │  langgraph_checkpoints  ││
│  └─────────────────────────┘│
└─────────────────────────────┘
```

## Phase 7: Cross-Investigation Intelligence (Future)
- [ ] **FalkorDB**: Persistent graph database for cross-investigation IOC and campaign correlation. Replaces per-investigation NetworkX for historical analysis.
- [ ] **Multi-container support**: Share investigation graph state across Cloud Run instances.
- [ ] **Advanced graph queries**: Cypher-based queries across historical investigations (e.g., "find all investigations linked to this C2 IP").
- [ ] **Microservices Split**: *If* scaling requires it, extract the MCP server into a dedicated Cloud Run service (Sidecar).

## Long-Term Exploration
- [ ] **Cloud Spanner + SpannerGraph**: Potential migration path from Cloud SQL + FalkorDB to a single GCP-native database handling both relational and graph workloads. Evaluate once LangGraph checkpointer compatibility with Spanner's PostgreSQL dialect is confirmed.

## Long-Term Enhancements
- [ ] **Advanced Graph Visualization**: Migrate from `streamlit-agraph` to more professional library:
    - **Option 1**: Pyvis (quick upgrade, better physics/interactivity)
    - **Option 2**: Plotly + NetworkX (enterprise-grade, actively maintained)
    - **Option 3**: Custom D3.js component (ultimate flexibility for threat intel workflows)
    - **Option 4**: Streamlit-Cytoscape, but haven't been actively maintained. 
    - Evaluation criteria: performance with 150+ nodes, layout algorithms (hierarchical, timeline), clustering capabilities
- [ ] **Future Investigation Workflow**: Full investigation flow with creation of hunt package

```
graph TD
    Start([IOC Submitted]) --> Triage[Triage Agent]
    
    Triage -->|Extract Targets & Assign Tasks| SpecialistGate{Specialist Gate}
    
    subgraph IterationLoop [Investigation Cycle - Max 3 Loops]
        direction TB
        SpecialistGate -->|Parallel Execution| Malware[Malware Agent]
        SpecialistGate -->|Parallel Execution| Infra[Infrastructure Hunter]
        SpecialistGate --> |Optional| Osint[OSINT Agent]
    end
    
        Malware --> LeadReview[Lead Threat Hunter]
        Infra --> LeadReview
        Osint --> LeadReview
        
        LeadReview -->|Analyze Reports & Gap Analysis| LoopCheck{Loop < 3?}
        LoopCheck -->|Yes: Issue Directives| SpecialistGate

    LoopCheck -->|No / Satisfied| Consolidation[Final Consolidation]
    LeadReview -->|Satisfied| Consolidation
    
    Consolidation -->|Synthesize Narrative| ReportGenerator[Lead Report Generator]
    ReportGenerator --> Detection[detection_agent]
    ReportGenerator -->|Final Markdown + Diagrams| End([Threat Intel Threat Hunt Complete])

    %% Styling for visual clarity
    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style End fill:#f9f,stroke:#333,stroke-width:2px
    style Triage fill:#bbf,stroke:#333,stroke-width:1px
    style Malware fill:#dfd,stroke:#333,stroke-width:1px
    style Infra fill:#dfd,stroke:#333,stroke-width:1px
    style Osint fill:#dfd,stroke:#333,stroke-width:1px
    style LeadReview fill:#fdd,stroke:#333,stroke-width:1px
    style Consolidation fill:#f96,stroke:#333,stroke-width:2px
    style Detection fill:#6fb,stroke:#333,stroke-width:2px

```

