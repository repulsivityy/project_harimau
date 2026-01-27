# Instructions [Project Harimau V2]

## Project Purpose
Cloud-native AI threat hunting platform using **LangGraph** for orchestration and **in-memory NetworkX** for investigation caching.

## Core Architecture Rules
1. **Micro-Modular Architecture**:
   * **Backend (`/backend`)**: FastAPI + LangGraph. Handles state, agents, and investigations.
   * **Frontend (`/app`)**: Streamlit. Pure UI, communicates with Backend via API.
2. **MCP Strategy**:
   * **Deployment**: Embedded within Backend container (Monolith).
   * **Transport**: `stdio` + Direct `aiohttp` (Parallel Super-Bundle) for zero-latency.
   * **Source**: Official GTI server from `elevate_2025` + Optimized Direct Fast-Path.
3. **Orchestrator**: LangGraph with `MAX_DEPTH` recursion control.
4. **Investigation Cache**: **NetworkX MultiDiGraph** (in-memory, per-job).
   * Stores full entity attributes from GTI API.
   * LLM queries minimal fields; specialists query full data.
   * Graph persists in LangGraph state for entire investigation.
5. **Compute**: Google Cloud Run (Serverless).
6. **Deployment**: Selective updates via `deploy.sh` (Backend/Frontend/All).

## Agent Strategy
* **Tiered Models**: Gemini 2.5 Flash (Triage) vs Gemini 2.5 Pro (Analysis).
* **Division of Labor**:
  - **Triage**: Breadth-first (11 critical relationships, minimal enrichment, token-optimized).
  - **Specialists**: Depth-first (full enrichment from cache, targeted pivots).
* **Config-Driven**: Agent behaviors defined in `agents.yaml`.
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

## Recent Bug Fixes
* **UnboundLocalError**: Fixed variable shadowing (`gti` → `gti_data`) in triage agent.
* **Empty Tooltips**: Added rich entity fields for mouseover.
* **Truncated URLs**: Now storing and displaying full URLs.

## Roadmap & Reliability
* **Investigation Cache**: NetworkX (MVP) → FalkorDB (Production, when ready).
* **Authentication**: Polling (MVP) → SSE (Phase 5).
* **Resiliency**: LangGraph Checkpointing (Phase 5) for crash recovery.
