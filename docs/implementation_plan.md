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
*   **Async Robustness**: Discovered that `asyncio.TaskGroup` is extremely fragile when consuming iterators (like VT API). A single 404/API error would crash the entire group. Implemented local try/except in `consume_vt_iterator` to ensure partial success doesn't trigger a total specialist failure.
*   **Variable Scoping**: Patched a critical `UnboundLocalError` where specialist nodes attempted to use `iteration` before definition. Always use `state.get("iteration", 0)` for safety.
*   **Parameter Propagation**: Found that `descriptors_only=True` was being dropped in nested relationship calls. Explicitly adding it to the `params` dict significantly improved specialist performance.

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
*   [x] **Graph-Aware Final Synthesis**: Lead Hunter final report now combines triage context, specialist summaries, and a compact summary derived from the persisted NetworkX investigation graph.

### Milestone 2: Performance & Token Optimization ✅
*   [x] **Sub-3s Triage**: Parallel `aiohttp` enrichment for immediate frontend feedback.
*   [x] **Dual-Layer Data Model**: Store rich metadata (150+ fields) but send minified summaries (<10 fields) to LLM.
*   [x] **Results**: Token usage reduced from 200K-2M → <30K (-90%+) per investigation.

### Milestone 3: Background Processing & Parallel Scaling ✅
*   [x] **Async Processing**: GET/POST separation to prevent Cloud Run HTTP timeouts (8min investigations).
*   [x] **Parallel Specialists**: Enabled Malware and Infra agents to run simultaneously.
*   [x] **Graph Reducer**: Implemented custom reducer to deep-merge parallel findings into the state.
*   [x] **CPU Optimization**: Deployed with `--no-cpu-throttling` to ensure background tasks complete post-request.

### Milestone 4: Flow & Robustness Refactoring ✅
*   [x] **Fix Parallel State Race Condition**: Refactor `subtasks` reducer in `state.py` (currently overwriting state due to parallel execution) by merging via task ID or moving status tracking solely to the orchestration nodes.
*   [x] **Consolidate Planning Roles**: Refactor workflow so Triage strictly outputs context/risk assessment, leaving all task planning to the Lead Hunter (e.g., Triage -> Lead Hunter Plan -> Specialists -> Lead Hunter Synthesize).
*   [x] **Strict Target Schemas**: Replace regex 'safety net' parsing in Specialists by enforcing strict JSON schemas for targets in the planner (deterministic routing).
*   [x] **Extract Inner Tool Loops**: (2026-06-04) Refactor specialist nodes (`infrastructure.py`, `malware.py`) to use Langgraph's native `ToolNode` and conditional edges instead of internal python `while/for` loops, improving checkpointing visibility and preventing thread blocking.
*   [x] **Restore Per-Tool Timeout & Catch-All**: (2026-07-29) Added `tool_timeout()` in `backend/utils/agent_utils.py`, applied under `@tool` on all 15 specialist tool closures. The `ToolNode` migration silently dropped the 20s budget and the catch-all that `run_tools_parallel` enforced — `ToolNode`'s default `handle_tool_errors` only converts `ToolInvocationError` and re-raises everything else, so an SSE failure in a tool's `emit_tool_call` hop (which sits outside each tool's own try/except) could abort an entire specialist. Also hoisted and hardened the sub-graph routers, and removed the dead `run_tools_parallel` / `cap_context_window` code.
*   [x] **Remove Duplicate Graph Expansion**: Remove post-LLM relationship expansion logic in specialists, relying solely on MCP tool wrappers to safely modify the graph cache during the natural reasoning loop.
*   [x] **Strict Structured Output**: (2026-06-04) Replace string parsing (`.replace("```json")`) with `with_structured_output()` to guarantee schema adherence and eliminate parsing fallbacks.
*   [x] **Optimize NetworkX MultiDiGraph Merges**: (2026-05-30) Implemented deep node attribute merging (unioned lists like `analyzed_by`) and robust pre-insertion edge deduplication in `InvestigationCache.add_relationship` and `merge_graphs` to prevent data loss and exponential edge duplication during parallel state merges.
*   [x] **Canonical Entity-ID Normalisation**: (2026-05-30) Implemented robust identifier normalisation (`_normalise_id`) across request intake (`main.py`), caching layers (`graph_cache.py`), Lead Hunter convergence detection, and UI root identification (`graph_formatter.py`) to prevent duplicate nodes and broken relationship links.
*   [x] **Typed IOC Identity Contract**: (2026-09-12) Replaced generic lowercasing with a shared file/IP/domain/URL identity contract across intake, graph cache, specialist selection, lifecycle/retry state, tool evidence, and graph formatting. URL identities lowercase only scheme/host and preserve path/query case. GTI URL base64 ids resolve to the canonical raw URL graph node and are retained as provenance aliases, preventing split nodes or accidental cache hits on a different case-sensitive URL resource.
*   [x] **URL Relationship Entities Keyed by GTI's Opaque SHA256 Id**: (2026-09-14) Some GTI relationship payloads identify `url` objects by a raw SHA256 object id rather than the base64url id the identity contract above decodes. Triage's relationship-ingestion loop now substitutes the entity's own `url`/`last_final_url` attribute as its graph/lifecycle identity in that case, retaining GTI's original id as `gti_id` provenance so existing id-based cache lookups still resolve — previously this fell back to an unrecognised `gti-url:<sha256>` identity that infrastructure-target matching silently rejected. `merge_graphs` was also normalising one side of a graph merge without its `entity_type`, which could split such an entity into two nodes when the two graphs disagreed on canonical form; both sides now normalise consistently.
*   [x] **Same Opaque-Id Gap Closed Centrally for Specialist Pivot Discovery** (found in 2026-09-14 review, fixed same day, corrected after a second review): the triage.py fix above was a call-site special case, not a change to `InvestigationCache.add_entity` itself — `infrastructure.py`'s three `get_entities_related_to_a_domain`/`_an_ip_address`/`_an_url` tools and `malware.py`'s `get_network_activity` still called `cache.add_entity` with GTI's raw relationship-item id for pivot-discovered `url` entities, hitting the same silently-dropped-lead bug (confirmed live: a real domain's `urls` relationship left 6 nodes stuck as `gti-url:<sha256>` in production). A first fix attempt made `add_entity`'s `url` branch call the pre-existing `_canonical_url_node_id` unconditionally, but this was inert at the very call sites it targeted — `extract_gti_summary` (which builds the attributes dict at those call sites) didn't carry `url`/`last_final_url` through from a relationship descriptor at all — and separately introduced a regression: attributes could override an already-decodable id, silently re-keying a URL investigation's root node whenever GTI's `url` attribute merely differed in spelling (e.g. a trailing slash) from the submitted IOC, verified live with `https://d.jennymodd.com` vs `https://d.jennymodd.com/`. An Opus 5 subagent review caught both issues before commit. Fixed properly: (1) `url`/`last_final_url` added to `extract_gti_summary`'s captured keys; (2) `add_entity`'s `url` branch now calls a new `_resolve_live_url_entity_id` — the caller's id is tried first and never overridden once it decodes, only an undecodable opaque id falls back to the `url` attribute, and `last_final_url` (a redirect target, not another spelling) is never consulted on this live path. `add_relationship`'s existing `_resolve_entity_id` alias matching on `gti_id` resolves edges to the same node with no further change. Rewrote the regression test to build attributes via the real `extract_gti_summary(descriptor_item)` path (the original test's hand-built `{"url": ...}` dict couldn't have caught the inert-fix bug) and added two more: one pinning the root-id-not-overridden invariant, one pinning that `last_final_url` is never used as a live identity. 146/146 tests passing.
*   [x] **Evidence-Backed Target Completion**: (2026-09-12) `processed_entities` and graph `analyzed_by` now advance only when the current specialist attempt explicitly names the selected target, includes substantive target-level evidence, and has a successful tool call mapped to that target. Minimal per-agent/per-target outcome metadata records timeouts, missing final output, tool errors, omitted targets, unsupported assertions, and empty evidence. Failed targets receive priority over new planner work within the relevant specialist cap, remain retryable, and are appended as unresolved gaps at the iteration limit. Lifecycle and unresolved-gap state are retained in the completed job metadata. `tasked_entities` remains a legacy scheduled alias for persisted checkpoints. (2026-09-14) A tool-error envelope elsewhere in the same batch no longer marks an unrelated target with its own successful, evidence-backed tool call as failed — per-target success is tracked via tool-call-id provenance, not batch-wide. Malware/Infrastructure also now build their failure-path `specialist_attempt` record before the `try` block that can raise, so a cache-construction error can no longer skip recording the failed attempt.
*   [x] **Durable Specialist Evidence in the Per-Job Graph**: (2026-09-12) Malware and Infrastructure tool wrappers retain JSON-compatible outputs on the requested graph node with agent/tool/source/status provenance. Target-specific structured findings and relationship provenance are retained beside them; recursive graph fan-in preserves parallel evidence. Lead Hunter planning receives only bounded target summaries, never raw tool payloads.
*   [x] **Explicit Enrichment and Terminal Outcomes**: (2026-09-12) Direct GTI enrichment now distinguishes validated `no_data` from `failed` for root and every required relationship request without changing the existing payload shape. Missing/malformed descriptors or descriptors without a fetch link are failed enrichment, never empty evidence. Triage terminates only when *every* requested relationship fails outright — a total loss of root enrichment; (2026-09-14) a partial failure (e.g. one rate-limited relationship among several) is instead logged and carried forward as a coverage gap in `enrichment_outcomes`, and triage still corrects its LLM facts to describe only validated enrichment. Planning and typed synthesis outcomes cannot treat exceptions, blank reports, or generic fallback markdown as convergence/success. A coverage-unknown stage failure now terminates the job as `failed` and emits both the affected node's `*_failed` and terminal `investigation_failed` SSE events; retryable target-level specialist gaps remain completed hunts with visible gaps.

**Challenges & Learnings**
*   **Scheduling Is Not Completion**: A specialist cap makes the accepted plan larger than a single specialist pass. Reusing scheduling history for convergence silently drops deferred leads even though the graph correctly leaves them uninvestigated; completion history must be recorded independently.
*   **A Batch Verdict Is Not Target Evidence**: A specialist can return a valid-looking batch result while omitting one selected IOC, or after a tool failure. Treating that as success hides an intelligence gap; outcome state must require an explicit target match and evidence before changing graph lifecycle markers.
*   **Empty Is Evidence Only After Success**: An empty API list is meaningful only when the upstream call succeeded. Collapsing API, tool, planning, or synthesis failures into empty output allowed the orchestrator to claim convergence without knowing coverage; outcome status must travel with the data to the terminal job state.
*   **Node Completion Is a Semantic Claim**: A node that returns a persisted terminal-failure contract did execute correctly as code, but it did not complete its investigative purpose. SSE must publish `*_failed` in that case so the UI does not contradict the job's terminal state.
*   **Tool Messages Are Not Durable Evidence**: ToolNode messages can disappear at checkpoint recovery or parallel branch fan-in. The graph is the per-job source of truth, so preserve tool outputs there and expose only compact structured evidence to later planning.

### Milestone 5: Intelligence Overhaul (May 2026) ✅
*   [x] **Gemini 3 Migration**: Switched to official `ChatGoogleGenerativeAI` SDK using Gemini 3 Flash/Pro.
*   [x] **Deterministic Subtask Generation**: Built Python-based router in `triage.py` to replace LLM planning in the triage phase.
*   [x] **Triage Signal Filtering**: Implemented strict verdict/vendor-count filters to reduce noise.
*   [x] **Iteration-Aware Context**: Added cumulative finding awareness to specialist prompts.
*   [x] **Graph Grounding**: Implemented machine-readable edge tuples for the Lead Hunter to prevent diagram hallucinations.
*   [x] **Complete Edge Attributes Into Synthesis**: (2026-07-30) `_score_edges` now records `source_type`/`target_type`/`source_verdict` (it already computed the types and discarded them), and the two conflicting edge blocks the LLM used to see — `Key Edges` keyed on ids vs `_build_edge_tuples` keyed on display labels, with different attributes and different filters — are collapsed into one id-keyed fact table carrying both endpoints' type, verdict and threat score plus a `high_signal` flag. A missing GTI threat score renders `unknown` instead of a misleading `0` (presentation only; no score is derived). `_select_diagram_edges` gives high-signal edges first claim on the 40-edge budget, without which they were entirely evicted by root-adjacent noise — `_score_edges` sorts root-adjacent first and `max(source, target)` hands the root's own score to all its edges.
*   [x] **URL Ids Broke DOT Validation**: (2026-07-30) `parse_dot_structure` stripped `//` comments with a regex, so a URL entity id ate the rest of its line and destroyed the quote balance. The skeleton then failed to validate against *itself*, silently discarding the LLM's annotation on every report whose diagram contained a URL — i.e. most hunts, since `contacted_urls`/`embedded_urls`/`urls` are all in triage's `PRIORITY_RELATIONSHIPS`. Replaced with a quote-aware stripper.
*   [x] **Deterministic Graphviz Skeleton**: (2026-07-29) New `backend/utils/dot_builder.py` builds a complete, deterministic `digraph` directly from the NetworkX cache — keyed on real normalised entity ids, not `_node_label()` display names (which could collapse two distinct entities into one DOT node). The LLM now annotates that skeleton instead of authoring a diagram, and its output is structurally validated against the cache's own node/edge set with a fallback to the skeleton. This closes a silent failure: the frontend's `d3-graphviz` `renderDot()` is worker-based, so its `try/catch` never fires and malformed DOT rendered a blank panel with no error.

---

## Pillar 5: Persistence & State Management
> **Focus**: Database integration, state checkpointing, and long-term storage.

### Milestone 1: Cloud SQL & Checkpointing ✅
*   [x] **Relational Persistence**: Replaced `JOBS` dict with Cloud SQL (Postgres).
*   [x] **LangGraph Checkpointing**: Integrated `AsyncPostgresSaver` to persist graph snapshots.
*   [x] **Checkpoint-Safe Orphan Recovery** (2026-09-12): An orphaned `running` job resumes the existing `thread_id` with `ainvoke(None, config=...)`, rather than receiving a new initial state that resets iteration/subtask control state. The complete request configuration is stored in job metadata at creation (currently `max_iterations`) and retained through completion for recovery. A readable checkpoint is resumed even when its graph has reached `END`, allowing the worker to finish persistence after a crash between graph completion and `save_job`; recovery is deferred without changing status only when checkpoint access is unavailable. (2026-09-14) Fixed a detection gap: `aget_state()` always returns a `StateSnapshot` object, even for a `thread_id` with no persisted checkpoint at all, so the original `if not snapshot` check could never identify that case — a snapshot with empty `values` and empty `next` is now also treated as unresumable.
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
*   [x] **SSE Failure Containment**: (2026-07-30) `sse_manager.emit_event` can no longer raise to its caller, and the emits in `with_sse_events` plus the three `transparency.py` helpers (awaited from inside `@tool` bodies) are each individually guarded. The `_started` emit previously sat outside the node's `try`, so a broadcast failure stopped the node from running at all. Broadcast now snapshots the subscriber list, fixing a silent-drop bug where a disconnecting client mutating the list mid-iteration caused later subscribers to be skipped.
*   [x] **Subtask-Aware Progress Curve**: (2026-07-30) `get_progress_estimate` now weights each iteration band by `len(state["subtasks"])`, advances on `triage` completion (previously a dead ternary returning 10 for both phases), and divides the band by `max_iterations + 1` — there are that many specialist passes, and dividing by `max_iterations` made specialists at the final iteration compute **103%**, clamped only client-side by `Math.min(pct, 100)`. Monotonicity and the 0-100 bound are enforced centrally by a per-job clamp in `sse_manager`, covering the hardcoded percentages in `main.py` too.
*   [x] **Agent Transparency**: Added "🔍 Agent Transparency" expander for tool traces and reasoning.
*   [x] **Durable Terminal SSE Reconciliation**: (2026-09-12) The stream registers its subscriber before snapshot emission, sends an authoritative persisted `investigation_snapshot` first, and recognizes completed/failed/cancelled terminal events. The page hydrates report, graph, timeline, and transparency data before stopping live updates; terminal status is monotone against stale REST responses. A bounded five-second REST reconciliation remains active beside SSE so a subscriber attached to a different Cloud Run instance still observes the durable terminal record. Cancellation is persisted as a terminal status and has its own `investigation_cancelled` event.
*   [x] **SSE Subscription Leak on Stream Setup Failure**: (2026-09-14) `GET /api/investigations/{job_id}/stream` opened its subscriber queue via `open_subscription()` before building the initial snapshot; if that lookup raised, the streaming generator whose `finally` normally closes the queue never started running, leaking the subscription. Setup is now wrapped so a failure closes the queue explicitly before re-raising.
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
*   [x] **Node Selection + Detail Panel**: `onNodeClick` handler that opens an interactive entity drawer showing full entity attributes from the persisted graph (threat score, vendor detections, relationships, verdict).
*   [x] **fitView & Recenter Button**: Trigger `fitView` imperatively via `useReactFlow()` on graph load and via a visible "Recenter" button.
*   [x] **Control Panel & Legend**: Small overlay panel explaining node colours/icons; toggle to hide clean nodes.

### Milestone 4: Threat Dossier Workbench & Server-to-Server API Hardening ✅
*   [x] **7-Section Threat Dossier Workbench** (2026-09-22): Migrated `/investigate/[id]` to the Harimau Threat Dossier layout (`DossierMasthead`, `SpecialistReportsGrid`, `DossierCompanionRail`, `AttackFlowSection`, `TacticalSwimLanes`, `DecoyInsightBanner`, `AppendixIocTable`) with dual view modes (`Threat Dossier` and `Spatial Topology Canvas`).
*   [x] **Redesigned Threat Dossier Landing Page** (2026-09-22): Updated `app/src/app/page.tsx` to match the Threat Dossier obsidian aesthetic (`#07090E` canvas, predatory tiger emblem `/tiger_logo.png`, 5-level Forensic Intensity selector, `HUNT` command CTA, and Recent Threat Dossiers list).
*   [x] **Isolated Frontend Test Suite (`app/tests/`)** (2026-09-22): Added 29 unit and SSR tests (`dossier-utils.test.ts`, `dossier-components.test.tsx`, `fixtures/etherrat-dossier.ts`) outside `app/src/`.
*   [x] **Fail-Closed Server-to-Server API Authentication (`x-harimau-api-key`)** (2026-09-22): Implemented shared `HARIMAU_API_KEY` (`harimau-api-key` in GCP Secret Manager) verified in constant time (`secrets.compare_digest`) by `backend/main.py` and injected by `app/src/app/api/[...path]/route.ts`. Both `harimau-backend` and `harimau-frontend` fail closed (`os._exit(1)` / `process.exit(1)`) and log a critical/fatal error at startup (`lifespan` / `instrumentation.ts`) and runtime if `HARIMAU_API_KEY` is missing.
*   [x] **Anti-Recon & Proxy Hardening** (2026-09-22): Disabled FastAPI `/docs`, `/redoc`, and `/openapi.json`; replaced client header pass-through in `route.ts` with a strict allowlist; blocked `/api/admin/*`, `/api/debug/*`, `/api/diagnostic/*`, and `/api/test/*` (`403 Forbidden`); enforced `https://` for non-localhost `BACKEND_URL`; and added per-IP rate limiting (`10 requests / 5 min`) on `POST /api/investigate`.

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
