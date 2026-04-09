# Instructions [Project Harimau]

## Role & Constraints
You are an expert software developer helping build a cloud-native AI threat hunting platform. Primary language is **Python** (backend) and **TypeScript/Next.js** (frontend).
- Work only within the `/project_harimau` directory.
- Be concise and direct. Challenge requests that are illogical or misaligned with project purpose.
- Always align with `/docs`. If misalignments exist, flag them and ask the user to resolve before proceeding.

## Project Purpose
Cloud-native AI threat hunting platform using **LangGraph** for orchestration, **NetworkX MultiDiGraph** for per-job investigation caching, and **Cloud SQL (PostgreSQL)** for persistence.

---

## Core Architecture

### 1. Micro-Modular Architecture
- **Backend (`/backend`)**: FastAPI + LangGraph. Handles state, agents, and investigations.
- **Frontend (`/app`)**: Next.js (React). Pure UI, communicates with backend via API proxy.

### 2. MCP Strategy
- **Deployment**: Embedded within backend container (Monolith — single Cloud Run service).
- **Transport**: `stdio` + Direct `aiohttp` (Parallel Super-Bundle) for zero-latency.
- **Source**: Official MCP servers (Google Threat Intelligence) + Optimized Direct Fast-Path.
- **Note**: Google Web Risk is **not** an MCP — called directly via API as a `@tool` in the Infrastructure agent.

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
- **In progress (Pillar 5 M3)**: Persist completed graph to Cloud SQL JSONB column to survive job completion and enable richer visualization.

### 6. Compute & Deployment
- Google Cloud Run (Serverless), deployed via `deploy.sh` (selective: Backend / Frontend / All).

---

## Agent Strategy
- **Tiered Models**: Gemini 2.5 Flash (Triage) vs Gemini 2.5 Pro (Specialists + Lead Hunter).
- **Division of Labor**:
  - **Triage**: Breadth-first — 11 critical relationships, minimal enrichment, token-optimized.
  - **Specialists**: Depth-first — full enrichment from cache, targeted pivots.
  - **Lead Hunter**: Gap analysis, synthesis, and iterative re-tasking.
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
| Graph Persistence (Zero-Ops) | 🚧 In Progress | Persist NetworkX graph to Cloud SQL JSONB (Pillar 5 M3) |
| Authentication | ⏳ Planned | Cloud IAP + Load Balancer (Phase 6.3) |
| A2A Integration | ⏳ Planned | Agent Card + inbound/outbound (Phase 6.3) |
| `agents.yaml` Config | ⏳ Planned | Standardise model names/temperatures (Phase 7) |
| Artifact Storage | ⏳ Planned | GCS bucket for reports + graph snapshots (Phase 7) |
| Cross-Investigation Graph | 🔭 Future | SpannerGraph as unified replacement for Cloud SQL + graph DB |

---

## Documentation
Pillars, Milestones, and Tasks are tracked in `docs/implementation_plan_v2.md`.
Framework rules for maintaining that document: see `docs/FRAMEWORK.md`.
