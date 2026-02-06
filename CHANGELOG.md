# Changelog

All notable changes to Project Harimau will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-02-07

### Added
- Agent tasks now displayed in collapsible expander in Triage tab for cleaner UI
- Full SHA256 hash display in graph nodes (no truncation)
- Graphviz diagram enforcement for top-to-bottom layout (`rankdir=TB`)
- Future agent roadmap documented: OSINT, Detection Engineering, SOC agents

### Changed
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
- Increased agent iteration limit from 3 to 7 for comprehensive analysis
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
- **LLM**: Google Vertex AI (Gemini 2.0)
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
