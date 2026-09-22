# Instructions [Project Harimau]


## Role & Constraints
You are an expert software developer helping build a cloud-native AI threat hunting platform. Primary language is **Python** (backend) and **TypeScript/Next.js** (frontend).
- Work only within the `/project_harimau` directory.
- Be concise and direct. Challenge requests that are illogical or misaligned with project purpose.
- Always align with `/docs`. If misalignments exist, flag them and ask the user to resolve before proceeding.
- **DO NOT** attempt to run anything locally unless specifically asked (eg, npm build, etc). 
- For any refactors or major changes, create a unit test to test the logic flow, and update the user on the results of the test. You can populate it with dummy data if necessary. 

## Project Purpose
Cloud-native AI threat hunting platform using **LangGraph** for orchestration, **NetworkX MultiDiGraph** for per-job investigation caching, and **Cloud SQL (PostgreSQL)** for persistence.

---

## Core Architecture

### 1. Micro-Modular Architecture
- **Backend (`/backend`)**: FastAPI + LangGraph. Handles state, agents, and investigations. Protected by fail-closed server-to-server `x-harimau-api-key` verification (`HARIMAU_API_KEY`) with public `/docs`, `/redoc`, and `/openapi.json` disabled.
- **Frontend (`/app`)**: Next.js (React). Harimau Threat Dossier workbench & Spatial Topology Canvas. Communicates with backend via hardened API proxy (`src/app/api/[...path]/route.ts`) that enforces fail-closed `HARIMAU_API_KEY` validation (`src/instrumentation.ts`), header allowlisting, admin path blocking, HTTPS transport verification, and IP rate-limiting on `POST /api/investigate`. Frontend unit/SSR tests and fixtures live in `app/tests/` (outside `app/src/`).

### 2. MCP Strategy
- **Deployment**: Embedded within backend container (Monolith — single Cloud Run service).
- **Transport**: `stdio` + Direct `aiohttp` (Parallel Super-Bundle) for zero-latency.
- **Source**: Official MCP servers (Google Threat Intelligence) + Optimized Direct Fast-Path.
- **Note**: Google Web Risk is **not** an MCP — called directly via API as a `@tool` in the Infrastructure agent.
- **⚠️ Version Pin**: `mcp==1.29.0` is pinned deliberately — it is the last release shipping `mcp.server.fastmcp`, which both `backend/mcp/gti/server.py` and `backend/mcp/shodan/server.py` import. **Do not bump to 2.x** without a migration: 2.x replaces `FastMCP` with a new `MCPServer` class and drops `stateless_http`. Tracked in `docs/implementation_plan.md` Pillar 7 Milestone 2.

### 3. A2A Integration *(Phase 6.3 — Planned)*
- **Inbound**: Expose `/.well-known/agent.json` + `POST /a2a/tasks/send` for external agent triggers.
- **Outbound**: On completion, optionally forward report to `detection_agent` via A2A.
- **Control**: Backend-only via `DETECTION_AGENT_ENABLED` + `DETECTION_AGENT_URL` env vars. Frontend is unaware.
- **Toggle without redeployment**: `gcloud run services update harimau-backend --set-env-vars DETECTION_AGENT_ENABLED=true,DETECTION_AGENT_URL=https://...`

### 4. Orchestrator
LangGraph with `MAX_DEPTH` recursion control and **Cloud SQL `AsyncPostgresSaver`** checkpointing for resiliency.

### 5. Investigation Cache
**NetworkX MultiDiGraph** — in-memory, per-job, lives in LangGraph state for the full investigation duration.
- Stores complete GTI entity attributes (150+ fields).
- LLM receives filtered summaries (<10 fields). Specialists query full data from cache — no re-fetching.
- **Persisted (Pillar 5 M3)**: Completed graphs are serialized to the Cloud SQL `investigation_graph` JSONB column to survive job completion and power the Threat Dossier and Spatial Topology Canvas.

### 6. Compute & Deployment
- Google Cloud Run (Serverless), deployed via `deploy.sh` (selective: Backend / Frontend / All) or automated Cloud Build (`cloudbuild-backend.yaml`, `cloudbuild-frontend.yaml`). Both services require `HARIMAU_API_KEY` (`harimau-api-key` in Secret Manager) and fail closed on startup/runtime if absent.
- **Runtimes**: Backend `python:3.14-slim`, Frontend `node:22-alpine` (Active LTS). Keep local dev interpreters aligned with these — dev/prod drift hides version-specific failures until deploy.
- **Dependency Policy**: `app/package-lock.json` is **tracked in git** and the frontend image installs with `npm ci`, not `npm install`. The lockfile is the only thing pinning the transitive tree with integrity hashes, and `npm ci` requires it to be present in the Cloud Build context — do not re-add it to `.gitignore`.

---

## Agent Strategy
- **Tiered Models**: Gemini 3 Flash (Triage) vs Gemini 3.1 Pro (Specialists + Lead Hunter).
- **Division of Labor**:
  - **Triage**: Breadth-first analysis — fetches 11 critical relationships, performs threat assessment and narrative reporting. No longer generates subtasks; routing is handled deterministically by a Python function based on analysis results.
  - **Lead Hunter**: The sole planning agent — consumes triage analysis and specialist findings to identify intelligence gaps and prioritize next-iteration leads. Also performs final synthesis.
  - **Specialists**: Depth-first — full enrichment from cache, targeted pivots. Now "Iteration-Aware": prompts include context about previous findings to ensure cumulative reporting.
- **Triage Signal Filtering**:
  - To minimize noise and token waste, triage only passes "High-Signal" entities to the LLM and subtask generator.
  - **Thresholds**: Entity must have a GTI verdict of `Malicious` or `Suspicious`, OR have `malicious_vendor_count > 3`.
  - **Exemptions**: Attribution relationships (associations, campaigns, actors) always bypass filtering to preserve context.
- **Config-Driven**: Agent parameters (`agents.yaml`) planned for Phase 7. Currently hardcoded per agent.
- **Tool Registry**: Dynamic loading via `mcp_registry.json`.

---

## Data Flow Pattern
1. **Fetch Everything**: Triage fetches full entities + relationships from GTI.
2. **Store Everything**: Full attributes stored in NetworkX graph (in LangGraph state).
3. **Query Minimal**: LLM gets filtered summaries (token-efficient).
4. **Enrich On-Demand**: Specialists pull full data from cache — no re-fetch.

**Token results**: <30K tokens per investigation (down from 200K–2M, -90%+).

---

## Roadmap & Current State

| Capability | Status | Notes |
|---|---|---|
| Cloud SQL Persistence | ✅ Complete | `investigations` table + JSONB metadata |
| LangGraph Checkpointing | ✅ Complete | `AsyncPostgresSaver` via Cloud Run unix socket |
| SSE Real-time Streaming | ✅ Complete | Replaced polling for live agent activity |
| Shodan Enrichment | ✅ Complete | JARM, SSL/TLS, service exposure in Infra agent |
| Graph Persistence (Zero-Ops) | ✅ Complete | Persist NetworkX graph to Cloud SQL JSONB (Pillar 5 M3) |
| Threat Dossier Workbench & Spatial Canvas | ✅ Complete | 7-section Threat Dossier UI, Spatial Topology Canvas, `app/tests/` suite |
| Server-to-Server API Authentication | ✅ Complete | Fail-closed `x-harimau-api-key` (`HARIMAU_API_KEY`) + proxy hardening |
| Authentication (End-User) | ⏳ Planned | Cloud IAP + Load Balancer (Phase 6.3) |
| A2A Integration | ⏳ Planned | Agent Card + inbound/outbound (Phase 6.3) |
| `agents.yaml` Config | ⏳ Planned | Standardise model names/temperatures (Phase 7) |
| Artifact Storage | ⏳ Planned | GCS bucket for reports + graph snapshots (Phase 7) |
| Cross-Investigation Graph | 🔭 Future | SpannerGraph as unified replacement for Cloud SQL + graph DB |

---

## Documentation
Pillars, Milestones, and Tasks are tracked in `docs/implementation_plan.md`.
Framework rules for maintaining that document: see `docs/FRAMEWORK.md`.
