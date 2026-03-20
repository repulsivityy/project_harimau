# Instructions [Project Harimau]

## Task
You are a expert software developer to help build a cloud-native AI threat hunting platform using **LangGraph** for orchestration and **in-memory NetworkX** for investigation caching.
The primary language for this project is **Python**.
You are provided with the source code of the project in the directory `/project_harimau`.
Do not modify any files outside of the `/project_harimau` directory.
Be concise and direct, challenge the user if any of their requests are illogical or not aligned with the project purpose.
If you require any additional information, please ask the USER. 
Always align with the documentation provided in the `/docs` directory. If there are any misalignments, inform the user and ask the user to resolve it.

## Project Purpose
Cloud-native AI threat hunting platform using **LangGraph** for orchestration and **in-memory NetworkX** for investigation caching.

## Core Architecture Rules
1. **Micro-Modular Architecture**:
   * **Backend (`/backend`)**: FastAPI + LangGraph. Handles state, agents, and investigations.
   * **Frontend (`/app`)**: Streamlit. Pure UI, communicates with Backend via API.
2. **MCP Strategy**:
   * **Deployment**: Embedded within Backend container (Monolith).
   * **Transport**: `stdio` + Direct `aiohttp` (Parallel Super-Bundle) for zero-latency.
   * **Source**: Official MCP servers (Google Threat Intelligence) + Optimized Direct Fast-Path.
   * **Note**: Google Web Risk is **not** an MCP — it is called directly via API as a `@tool` in the Infrastructure agent.
3. **A2A Integration** (Phase 6):
   * **Inbound**: Harimau exposes A2A-compatible endpoints (`/.well-known/agent.json` Agent Card + `POST /a2a/tasks/send`) so external agents (e.g. detection_agent) can trigger investigations.
   * **Outbound**: On investigation completion, Harimau optionally forwards the report to the detection_agent via A2A.
   * **Control**: Backend-only via `DETECTION_AGENT_ENABLED` + `DETECTION_AGENT_URL` env vars on the Cloud Run service. Frontend is unaware.
   * **Toggle without redeployment**: `gcloud run services update harimau-backend --set-env-vars DETECTION_AGENT_ENABLED=true,DETECTION_AGENT_URL=https://...`
4. **Orchestrator**: LangGraph with `MAX_DEPTH` recursion control.
5. **Investigation Cache**: **NetworkX MultiDiGraph** (in-memory, per-job).
   * Stores full entity attributes from GTI API.
   * LLM queries minimal fields; specialists query full data.
   * Graph persists in LangGraph state for entire investigation.
6. **Compute**: Google Cloud Run (Serverless).
7. **Deployment**: Selective updates via `deploy.sh` (Backend/Frontend/All).

## Agent Strategy
* **Tiered Models**: Gemini 2.5 Flash (Triage) vs Gemini 2.5 Pro (Analysis).
* **Division of Labor**:
  - **Triage**: Breadth-first (11 critical relationships, minimal enrichment, token-optimized).
  - **Specialists**: Depth-first (full enrichment from cache, targeted pivots).
* **Config-Driven**: Agent tuning parameters (model, iterations, max targets, feature flags) to be defined in `agents.yaml` (Phase 6). Currently hardcoded per agent.
* **Tool Registry**: Dynamic loading via `mcp_registry.json`.

## Data Flow Pattern (Alpha-Inspired)
1. **Fetch Everything**: Triage agent fetches full entities + relationships from GTI.
2. **Store Everything**: Full attributes stored in NetworkX graph (in LangGraph state).
3. **Query Minimal**: LLM gets filtered summaries (token-efficient).
4. **Enrich On-Demand**: Specialists pull full data from cache (no re-fetch).

## Token Optimization
* **File IOC Relationships**: 20 → 11 critical types (-45%).
* **Entity Storage**: Full attributes in NetworkX graph.
* **LLM Context**: Filtered to 9 essential fields (-95% per entity).
* **Result**: <30K tokens for file investigations (down from 200K-2M).

## Graph Visualization
* **Display Fields**: Full URLs, filenames, size, categories, threat scores.
* **Tooltips**: Human-readable format showing:
  - Threat score
  - "X vendors detected as malicious"
  - File info (name, type, size)
  - URL categories
  - Verdict

## Roadmap & Reliability
* **Investigation Cache**: NetworkX (MVP) → FalkorDB (Phase 7, cross-investigation graph queries).
* **Persistence**: Cloud SQL PostgreSQL (Phase 6) for investigation storage + LangGraph checkpointing.
* **Artifact Storage**: GCS bucket for completed reports and graph state (Phase 6).
* **Authentication**: Polling (MVP) → SSE (Phase 6, partially implemented).
* **Resiliency**: LangGraph Checkpointing (Phase 6) for crash recovery.
* **Long-Term**: Explore Cloud Spanner + SpannerGraph as a unified replacement for Cloud SQL + FalkorDB.
