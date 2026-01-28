# Project Harimau

**Cloud-Native AI Threat Hunter**

Project Harimau is an automated threat investigation platform using a graph-based multi-agent system (LangGraph) to mimic SOC team workflows.

## Architecture
* **Frontend**: Streamlit (Cloud Run Service).
* **Backend**: FastAPI + LangGraph (Cloud Run Service).
* **MCP**: Embedded GTI Server (stdio/Direct API).
* **Brain**: Gemini 2.5 Flash / Pro.
* **Investigation Cache**: NetworkX (in-memory graph per job).

## Features
* **Rich Visualization**: Full URLs, filenames, threat scores in graph tooltips.
* **Modularity**: Add tools via `mcp_registry.json` and agents via `agents.yaml`.
* **Reliability**: Async architecture handles long investigations without timeouts.
* **CostSafe™**: Built-in recursion depth limits.

## 🚀 Deployment (GCP)
1. **Prerequisites**: `gcloud` CLI installed and authenticated.
2. **Configuration**:
   ```bash
   # Export your GTI API Key (saved to Secret Manager)
   export GTI_API_KEY="your_actual_key_here"
   ```
3. **Deploy**:
   ```bash
   ./deploy.sh [backend|frontend|all]
   ```
   - **Default**: Deploys both.
   - **Backend only**: `./deploy.sh backend`
   - **Frontend only**: `./deploy.sh frontend`

4. **Verify**:
   ```bash
   curl -X POST "https://harimau-backend-<PROJECT_ID>.asia-southeast1.run.app/api/investigate" \
        -H "Content-Type: application/json" \
        -d '{"ioc": "44d88612fea8a8f36de82e1278abb02f"}'
   ```

## 📊 Status
- **Phase 1 (Infrastructure)**: ✅ Complete
- **Phase 2 (The Brain)**: ✅ Complete
- **Phase 3 (Interface)**: ✅ Complete
- **Phase 4 (Hybrid Triage + Token Optimization)**: ✅ Complete
- **Phase 5 (Enhanced Visualization + NetworkX Cache)**: 🚧 In Progress
- **Phase 6 (Specialist Agent Expansion)**: 📋 Planned

## Quick Start (Local)

1. **Clone & Env**:
   ```bash
   cp .env.example .env
   # Add GTI_API_KEY
   ```

2. **Run Backend**:
   ```bash
   cd backend && uvicorn main:app --reload
   ```

3. **Run Frontend**:
   ```bash
   cd app && streamlit run main.py
   ```

## Architecture Principles

### Data Flow
1. **Fetch Full**: Triage fetches complete entity data from GTI
2. **Store All**: Full attributes cached in NetworkX graph (LangGraph state)
3. **Query Minimal**: LLM receives filtered summaries (token-efficient)
4. **Enrich On-Demand**: Specialists pull from cache (no re-fetch)

### Agent Division
- **Triage**: Breadth-first (11 relationships, minimal context, <30K tokens)
- **Specialists**: Depth-first (full enrichment, targeted analysis)

## Documentation
* [Product Requirements (PRD)](docs/PRD.md)
* [Architecture Proposal](docs/architecture.md)
* [Implementation Plan](docs/implementation_plan.md)

## Technology Stack
- **Orchestration**: LangGraph
- **API**: FastAPI
- **UI**: Streamlit
- **LLM**: Vertex AI (Gemini 2.5)
- **Cache**: NetworkX (in-memory)
- **Deployment**: Google Cloud Run
- **Secrets**: Google Secret Manager
