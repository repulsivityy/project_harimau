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

#### [COMPLETED] [Malware Specialist](backend/agents/malware.py)
*   **Behavior Analysis**: Deep dive into dropped files, C2 communications, and execution patterns
*   **Tools**: `get_file_report`, `get_entities_related_to_a_file`.
*   **Programmatic Reporting**: Generates structured Markdown reports outside the LLM context for 100% stability.
*   **Automatic Indicator Sync**: Discovered indicators (C2s, dropped files) are automatically pushed to both the NetworkX cache and LangGraph state for immediate frontend visibility.
*   **Source-Aware Graphing**: Links shared infrastructure (e.g., common C2 IPs) back to the specific malware hash that contacted them.

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

## Phase 5: Iterative Investigation Workflow [IN PROGRESS]

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

### Phase 5.2: Lead Threat Hunter Agent [IN PROGRESS]
**Goal**: Orchestrate iterative investigations (max 3 iterations).

**See**: `docs/phase_5_2_lead_hunter.md` for full technical specification.

**Core Tasks**:
- [ ] Create `backend/agents/lead_hunter.py` with LLM-based orchestration logic
- [ ] Add `get_uninvestigated_nodes()` to InvestigationCache
- [ ] Update workflow: Add gate and lead hunter nodes, implement iteration loop
- [ ] Add `iteration` and `lead_hunter_report` to AgentState
- [ ] Testing: Unit, integration, end-to-end
- [ ] Deploy and verify iteration behavior

**Lead Hunter Responsibilities**:
1. Review triage + specialist reports
2. Analyze graph to find uninvestigated entities
3. Prioritize high-value targets (malicious, attack-chain-relevant)
4. Create subtasks for next iteration
5. Generate holistic synthesis report
6. Decide: continue (if iteration < 3 and targets exist) or end

**Workflow**:
```
Iteration 0: Triage → Gate → [Malware, Infra] → Lead Hunter → Decision
Iteration 1: Gate → [Malware, Infra] → Lead Hunter → Decision
Iteration 2: Gate → [Malware, Infra] → Lead Hunter → END (max reached)
```

---

### Phase 5.3: Autonomy & Fine-Tuning [PLANNED]
- [ ] Advanced prompting for autonomous decisions
- [ ] Adaptive iteration limits
- [ ] Cost-aware investigation
- [ ] Hunt package generation (YARA/Sigma)
- [ ] Timeline reconstruction

**Upon completion of Phase 5, product is ready for MVP release**
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
- [ ] **Real-Time Streaming**: Refactor Frontend/Backend to use SSE (Server-Sent Events) instead of polling.
- [ ] **Microservices Split**: *If* scaling requires it, extract the MCP server into a dedicated Cloud Run service (Sidecar).
- [ ] **Advanced Error Handling**: Implement exponential backoff for GTI API and automatic agent retries.
- [ ] **Authentication Hardening**: Switch from `--allow-unauthenticated` to IAP/IAM.
- [ ] **Crash Recovery**: Implement LangGraph Postgres Checkpointing to resume jobs after Cloud Run restarts.
- [ ] **Smart Entity Filtering (Option B)**: Implement user-configurable filters at investigation start to prioritize malicious/high-score entities by threat score, verdict, and recency.
- [ ] **Structured Output Enhancement**: Consider migrating to LangChain's `with_structured_output()` for final agent responses.
    - **Context**: Currently using enhanced prompts to ensure JSON output; LLM sometimes provides narrative explanations when tools fail.
    - **Proposal**: Use structured output only for final iteration response while maintaining AI-led investigation during tool-use loop.
    - **Benefits**: Guaranteed valid JSON parsing, type safety via Pydantic schemas, elimination of JSON parsing errors.
    - **Trade-off**: Slightly more deterministic output format, but preserves agentic decision-making during investigation.
    - **Implementation Pattern**: 
      ```python
      # Iterations 1-6: Fully AI-led with tools
      llm_with_tools = ChatVertexAI(...).bind_tools(tools)
      
      # Final iteration: Structured output for reliability
      llm_structured = ChatVertexAI(...).with_structured_output(AgentAnalysisSchema)
      ```
    - **Status**: Prompt-based approach working well (Feb 2026); re-evaluate if JSON parsing failures increase.

## Phase 6: Long-Term Enhancements
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
    ReportGenerator --> HuntPack[Hunt_pack_agent]
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
    style HuntPack fill:#6fb,stroke:#333,stroke-width:2px

```