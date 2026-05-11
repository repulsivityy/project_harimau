# Changelog

All notable changes to Project Harimau will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Shared Agent Utilities** (`backend/utils/agent_utils.py`): Extracted common agent logic into a shared module — `parse_llm_json()`, `run_tools_parallel()`, `cap_context_window()`, and `push_to_rich_intel()`. Both specialist agents now import from this module, removing ~80 lines of duplicated code each.
- **threat_score field**: Both Malware and Infrastructure specialist agents now output a `threat_score` field read directly from `gti_assessment.threat_score.value` in the GTI tool response. No derivation or combination — direct passthrough.
- **Cross-agent collaboration instruction**: Infrastructure agent prompt now explicitly instructs the LLM to place file hashes found in `communicating_files` / `downloaded_files` into `related_indicators` with a `File:` prefix, so the Malware agent can pick them up in subsequent iterations.
- **Narrative summary field**: Both specialist agents now produce a 5-paragraph narrative in the `summary` field of their JSON output, giving the synthesis agent richer source material.
- **Context window cap**: `cap_context_window()` prevents unbounded message growth in the agent loop by keeping only the first 2 system messages and the last 10 messages (trimmed to start on an AIMessage to avoid orphaned ToolMessages).
- **Parallel tool execution with timeout**: `run_tools_parallel()` runs all LLM tool calls concurrently via `asyncio.gather` with a per-tool 20-second timeout.

### Fixed
- **Cloud Build Deployment Race Condition**: Fixed an issue in `cloudbuild-backend.yaml` and `cloudbuild-frontend.yaml` where `gcloud run deploy` was executing before the newly built container image was pushed to Artifact Registry, causing deployments to fail with stale image errors. Added explicit `docker push` steps.
- **Malware agent stale tool name**: `get_file_behavior_summary(hash)` → `get_file_behavior(hash)` to match actual MCP tool name.
- **Bare `except: pass` blocks**: Replaced silent exception suppression in both specialist agents with `except Exception as e: logger.warning(...)`.
- **Frontend build — `@types/d3-graphviz` version**: Package only publishes up to `2.6.10`; updated `app/package.json` from `^5.0.0` to `^2.6.10`.
- **Frontend build — graphviz `width`/`height` type error**: Options type requires `number`, not `string`; removed both fields (redundant with `fit: true`).
- **Database Schema**: Reverted `gti_score` column type from `VARCHAR(50)` back to `INTEGER` to enforce strict typing.
- **Data Integrity**: Removed aggressive `"N/A"` string coercion for missing threat scores. Missing scores now safely persist as `NULL` in the database.
- **Frontend Resilience**: Updated the tactical dashboard and modals to gracefully render "Unknown" when encountering `null` or missing threat scores.

## [0.5.0] - 2026-04-09

### Added
- **Next.js Frontend**: Completely rebuilt the user interface using Next.js (App Router, React, Tailwind CSS), replacing the legacy Streamlit application.
- **Real-Time Streaming**: Implemented Server-Sent Events (SSE) to replace the 10-second polling mechanism, providing sub-second, real-time updates for agent tasks and tool calls.
- **Shodan MCP Integration**: Added a Shodan FastMCP server to enrich the Infrastructure Agent with internet exposure data, port scans, and CVE lookups.
- **Configurable Investigation Depth**: Unified loop limiters into a single `max_iterations` state parameter, allowing users to control the depth of each hunt via a frontend slider.

### Fixed
- **Cloud SQL Connectivity**: Added necessary Terraform annotations (`run.googleapis.com/cloudsql-instances`) and Cloud Build flags to ensure the Cloud SQL Auth Proxy socket is correctly injected into the backend Cloud Run container.
- **Frontend API Routing**: Replaced build-time `next.config.ts` rewrites with a runtime catch-all API route (`app/src/app/api/[...path]/route.ts`) so the Next.js container correctly resolves the dynamic backend URL provided by Cloud Run.

## [0.4.0] - 2026-03-23

### Added
- **Cloud SQL Persistence**: Replaced in-memory `JOBS` dictionary with Cloud SQL (PostgreSQL) for durable investigation storage.
- **LangGraph Checkpointing**: Integrated `AsyncPostgresSaver` to persist investigation state snapshots, enabling survival across container restarts.
- **Durable Error Handling**: Hardened background task error handler to ensure failed investigations are always recorded in the database.
- **Advanced Logging**: Enhanced `save_job` error logs with `data_keys` and `metadata_keys` for rapid serialization debugging.

### Fixed
- **State Initialization**: Fixed `initial_state` missing core fields (`iteration`, `loop_count`, `investigation_graph`) that prevented workflow execution.
- **Serialization Safety**: Explicitly excluded non-serializable NetworkX graph objects from database persistence (reconstructed from `rich_intel` for UI).
- **Split-Brain Prevention**: Modified `get_job` to return `None` on database failure instead of falling back to potentially stale in-memory data.
- **Background Failures**: Fixed a race condition where investigations could be silently lost if the initial database save failed.

### Technical Details
- **Deployment**: Integrated `asyncpg` for app data and `psycopg` for LangGraph checkpoints.
- **Resiliency**: Investigations now resume from the last completed node after a crash or scale-down.
- **Integrity**: 22 new unit tests covering persistence flow logic and error boundaries.

## [0.3.1] - 2026-02-07

### Added
- Agent tasks now displayed in collapsible expander in Triage tab for cleaner UI
- Full SHA256 hash display in graph nodes (no truncation)
- Graphviz diagram enforcement for top-to-bottom layout (`rankdir=TB`)
- Future agent roadmap documented: OSINT, Detection Engineering, SOC agents

### Changed
- Increased agent iteration limit from 7 to 10 (`malware_iterations`, `infra_iterations`) for deeper analysis coverage
- **Code Cleanup**: Removed 49 lines of commented-out code across `malware.py`, `infrastructure.py`, `triage.py`
- **Code Cleanup**: Removed 9 outdated `[NEW]` markers from Jan 2026 features (now production-stable)
- **Code Cleanup**: Updated TODO comments to reference roadmap items (Phase 6)
- Graph node labels now show full hashes instead of truncated versions (e.g., `abcde...123ebf` → full SHA256)
- Comment numbering corrections in infrastructure markdown report generator
- Simplified verbose comments in `main.py` for better readability

### Documentation
- Updated `README.md` with "How it works" section
- Added future agent capabilities preview
- Updated `CHANGELOG.md` with recent improvements
- Updated `.gitignore` to exclude `test_*` files

### Fixed
- Infrastructure Agent now successfully processes IP addresses without validation errors
- Both agents robustly handle JSON responses in array or object format
- Subtask status updates now properly mark completed work
- Removed duplicate fallback logic in Infrastructure Agent

## [0.3.0] - 2026-01-30

### Added
- JSON array/object dual-format parsing for both specialist agents
- Comprehensive agent debugging guide (`docs/agent_debugging_guide.md`)
- Regex fallback for target discovery in Infrastructure Agent
- Explicit `entity_id` requirement in Triage Agent subtask generation

### Fixed
- **Critical**: MCP tool argument mapping (`ip` → `ip_address`) preventing IP analysis
- **Critical**: "LLM returned empty content" error via robust fallback logic
- **Critical**: "Extra data" JSON parsing errors when LLM returns arrays
- Missing Infrastructure Specialist reports due to early agent exit
- Duplicate fallback code blocks in agent loops
- Missing subtask status updates in Infrastructure Agent
- Syntax errors from aggressive variable renaming (`reiteration` → `return`)

### Changed
- Increased agent iteration limit from 3 to 7 for comprehensive analysis (subsequently increased to 10 — see v0.3.1)
- Aligned Malware and Infrastructure agent code structures
- Removed Pydantic BaseModel schemas to prevent deployment crashes
- Enhanced error reporting from 500 to 2000 characters
- Improved fallback logic to strictly check for `AIMessage` content

### Technical Details
- **Deployment**: Cloud Run revision `harimau-backend-00139-sln`
- **Region**: asia-southeast1
- **Python Version**: 3.11+
- **Key Dependencies**: LangGraph, LangChain, FastAPI, Streamlit

## [0.2.0] - 2026-01-28

### Added
- NetworkX graph cache for entity relationship tracking
- Malware Specialist markdown report generation
- Infrastructure Specialist agent with network pivoting capabilities
- Graph visualization with tooltips and source-based clustering
- Crowdsourced AI results integration in Triage Agent
- Parallel agent execution with state merge reducers

### Fixed
- Backend 500 errors during parallel agent execution
- Graph centering issues on initial load
- Missing entity relationships in graph visualization
- Triage Agent JSON stability issues

### Changed
- Enhanced Malware Agent with attribution and dropped files analysis
- Improved graph node deduplication logic
- Updated API responses to include `specialist_results`

## [0.1.0] - 2026-01-27

### Added
- Initial Project Harimau V2 implementation
- LangGraph-based investigation workflow
- MCP integration for Google Threat Intelligence API
- Streamlit frontend with investigation graph
- FastAPI backend with async job processing
- Triage Agent with intelligent task decomposition
- Basic Malware Specialist agent

### Technical Stack
- **Frontend**: Streamlit (Python)
- **Backend**: FastAPI + LangGraph + NetworkX
- **LLM**: Google Vertex AI (Gemini 2.5)
- **API**: Google Threat Intelligence (via MCP)
- **Deployment**: Google Cloud Run
- **Graph Storage**: In-memory NetworkX MultiDiGraph

---

## Version Numbering

- **Major** (X.0.0): Significant architectural changes or backwards-incompatible updates
- **Minor** (0.X.0): New features, agent capabilities, or significant improvements  
- **Patch** (0.0.X): Bug fixes, documentation updates, minor tweaks

## Deployment History

| Revision | Date | Version | Notes |
|----------|------|---------|-------|
| 00139-sln | 2026-01-30 | 0.3.0 | JSON array handling, MCP fixes |
| 00137-tx5 | 2026-01-30 | 0.2.5 | MCP argument mapping |
| 00136-2b2 | 2026-01-30 | 0.2.4 | Fallback logic fix |
| 00135-dzs | 2026-01-30 | 0.2.3 | Structural alignment |
| 00134-2rj | 2026-01-29 | 0.2.2 | Pydantic removal |
| 00155-sql | 2026-03-23 | 0.4.0 | Cloud SQL + Checkpointing |
