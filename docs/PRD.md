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
3.  **Hybrid Triage Agent**: Classifies IOC using Fast Facts (Direct API) + Agentic Reasoning (Root Node).
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
*   **Comprehensive Relationship Coverage (52 types)**:
    - **File IOCs (20 relationships)**: `associations`, `bundled_files`, `contacted_domains`, `contacted_ips`, `contacted_urls`, `dropped_files`, `embedded_domains`, `embedded_ips`, `embedded_urls`, `email_attachments`, `email_parents`, `execution_parents`, `itw_domains`, `itw_ips`, `itw_urls`, `malware_families`, `memory_pattern_domains`, `memory_pattern_ips`, `memory_pattern_urls`, `attack_techniques`
    - **Domain IOCs (14 relationships)**: `associations`, `caa_records`, `cname_records`, `communicating_files`, `downloaded_files`, `historical_ssl_certificates`, `immediate_parent`, `parent`, `referrer_files`, `resolutions`, `siblings`, `subdomains`, `urls`, `malware_families`
    - **IP IOCs (6 relationships)**: `communicating_files`, `downloaded_files`, `historical_whois`, `referrer_files`, `resolutions`, `urls`
    - **URL IOCs (12 relationships)**: `communicating_files`, `contacted_domains`, `contacted_ips`, `downloaded_files`, `embedded_js_files`, `last_serving_ip_address`, `memory_pattern_parents`, `network_location`, `redirecting_urls`, `redirects_to`, `referrer_files`, `referrer_urls`
*   **Graph Visualization Strategy**:
    - **Display**: Only IOC-to-IOC relationships (files, domains, IPs, URLs, DNS records, SSL certs, etc.)
    - **Filter Out**: Contextual metadata (`attack_techniques`, `malware_families`, `associations`, `campaigns`, `related_threat_actors`) - still fetched/analyzed but not visualized
    - **Agent Nodes**: Internal workflow nodes (e.g., malware_specialist) are NOT shown in graph
*   **Capacity Limits**:
    - Fetch up to 10 entities per relationship type from GTI
    - Maximum 150 total entities across all relationships
    - Display up to 15 entities per relationship in graph UI
    - **Future**: Smart filtering to prioritize malicious/high-score entities (Option B)

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
*   **Deployment**: Support `deploy.sh` (selective backend/frontend updates) and `terraform/`.
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
