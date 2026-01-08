# Product Requirements Document (PRD): Project Harimau V2

> **Vision:** A scalable, open-source-friendly AI Threat Hunting platform that mimics a human SOC team using GraphRAG and specialist agents.

## 1. Objectives
*   **Cost-Effective**: Run primarily on GCP Free Tier (Cloud Run, Gemini Flash).
*   **Graph-Centric**: Maintain investigation state in a knowledge graph (GraphRAG).
*   **Agentic**: Use LangGraph to orchestrate multi-step investigations.
*   **Reliable**: Solution must handle long-running investigations (>5 mins) via Async Workers.
*   **Observable**: Deep visibility into Agent reasoning and Tool execution via tiered logging.

## 2. Technical Stack
*   **Frontend (`/app`)**: Streamlit (Cloud Run Service A).
*   **Backend (`/backend`)**: FastAPI + LangGraph (Cloud Run Service B).
*   **Database**: FalkorDB (Sidecar or Docker).
*   **MCP Server**: Google Threat Intelligence (Embedded Python Subprocess).
*   **Models**: Gemini 3.0 Flash (Triage) / Pro (Analysis).

## 3. Core Features

### 3.1 Architecture & Modularity
*   **Split Services**: Frontend (UI) and Backend (Logic) are separate to allow Async Worker patterns.
*   **Embedded MCP**: The GTI MCP server runs inside the Backend container via `stdio`.
*   **Config-Driven Agents**: Agents added via `agents.yaml`.
*   **MCP Registry**: Tools loaded dynamically from `mcp_registry.json`.

### 3.2 Investigation Workflow
1.  **Input**: User inputs IOC in Streamlit.
2.  **Async Queue**: Frontend posts job to Backend -> Backend offloads to Cloud Tasks.
3.  **Triage Agent**: Classifies IOC (Root Node).
4.  **Pivot (Recursion)**: Infra Agent / Malware Agent expands the graph.
5.  **Synthesis**: Lead Hunter writes the report.

**Report Format Requirements:**
The Lead Hunter must produce a **comprehensive narrative report**, not just a verdict. The report must include:
*   **Executive Summary**: One-paragraph verdict with confidence level.
*   **Attack Chain Narrative**: Explain HOW the malicious activity occurred (e.g., "The file attempted to execute code that downloaded a 2nd stage ransomware payload from domain X").
*   **Evidence**: List all IOCs discovered, their verdicts, and relationships.
*   **Technical Details**: Relevant TTPs, CVEs, campaign names from GTI.
*   **Recommended Actions**: Containment/remediation steps.

### 3.3 The Knowledge Graph
*   **Schema**: Hybrid (Fixed Layout Properties + Dynamic Intelligence Properties).
*   **Edges**: Automatic mapping from MCP response keys.

### 3.4 The Librarian (Async)
*   Runs *after* investigation completion.
*   Proposes Schema Cleanups (e.g. merging edge types).
*   Requires **Human Approval** via UI.

### 3.5 Artifact Persistence (Report & Graph)
*   **Storage**: Google Cloud Storage (GCS) Bucket.
*   **Graph Image**: Backend renders graph state to `graphviz` -> PNG.
*   **Report**: Backend saves final markdown to `.md`.
*   **Structure**: `gs://[bucket]/[job_id]/report.md` & `graph.png`.

## 4. Operational Requirements
*   **Deployment**: Support `deploy.sh` and `terraform/`.
*   **Security**: Auth (Phased), Secrets (Secret Manager).
*   **Observability (Logging)**:
    *   **Format**: Structured JSON (compatible with Cloud Logging).
    *   **Tier 1 (INFO)**: High-level milestones ("Job Started", "Verdict Reached").
    *   **Tier 2 (DEBUG)**: Deep Trace. Captures Agent "Thought", Tool Input/Output, and Raw API Payloads.
    *   **Context**: All logs must carry a `trace_id` or `job_id` to correlate Backend actions with Frontend requests.
*   **Resiliency (Phase 5)**:
    *   **State Recovery**: Must save LangGraph checkpoints to Postgres/Redis to allow resuming if the container crashes.
*   **Frontend UX**:
    *   **MVP**: Polling interval set to 10s (Configurable via `POLL_INTERVAL` env var).
    *   **Roadmap**: Migrate to SSE for sub-second updates.

## 5. Testing Strategy
We adopt a "Verify-as-we-Build" approach.
*   **Unit Tests (`pytest`)**:
    *   **Agents**: Test logic with *Mocked* LLM outputs (don't waste money).
    *   **Tools**: Test MCP Client parsing logic (Mocked MCP responses).
*   **Integration Tests**:
    *   **Workflow**: Run a full "Dry Run" investigation with a Mocked Graph to ensure edges traverse correctly.
*   **Infrastructure Tests**:
    *   **MCP**: Script to spin up the subprocess and verify it responds to `list_tools` via stdio.
    *   **DB**: Simple connection/write/read check.
