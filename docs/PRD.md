# Product Requirements Document (PRD): Project Harimau V2

> **Vision:** A scalable AI-powered threat intelligence analysis platform that analyzes IOCs from Google Threat Intelligence using multi-agent collaboration and knowledge graph reasoning.

## 1. Objectives
*   **Intelligence-Focused**: Analyze malware, map infrastructure, and synthesize threat intelligence reports
*   **Graph-Centric**: Maintain investigation findings in a knowledge graph for relationship discovery
*   **Agentic**: Use LangGraph to orchestrate multi-agent threat analysis workflows
*   **Scalable**: Handle deep investigations via async architecture on GCP Cloud Run
*   **Observable**: Deep visibility into agent reasoning and threat data exploration

## 2. Technical Stack
*   **Frontend (`/app`)**: Streamlit (Cloud Run Service) - Interactive investigation dashboard
*   **Backend (`/backend`)**: FastAPI + LangGraph (Cloud Run Service) - Multi-agent orchestration
*   **Cache**: NetworkX (in-memory graph per investigation)
*   **MCP Server**: Google Threat Intelligence (Embedded Python subprocess)
*   **Models**: Gemini 2.5 Flash (Triage) / Pro (Deep Analysis)

## 3. Core Features

### 3.1 Architecture & Modularity
*   **Split Services**: Frontend (UI) and Backend (Logic) run as separate Cloud Run services
*   **Embedded MCP**: GTI MCP server runs inside Backend container via `stdio`
*   **Config-Driven Agents**: Specialist agents defined in `agents.yaml`
*   **MCP Registry**: GTI tools loaded dynamically from `mcp_registry.json`

### 3.2 Threat Intelligence Workflow
1.  **Input**: User provides IOC (hash, domain, IP, URL) in Streamlit interface
2.  **Async Investigation**: Frontend submits job → Backend orchestrates multi-agent analysis
3.  **Triage Agent**: Initial classification and relationship discovery (breadth-first)
4.  **Specialist Agents** (parallel execution):
    - **Malware Specialist**: Behavioral analysis, capability assessment, attribution
    - **Infrastructure Specialist**: DNS mapping, hosting analysis, pivot detection
5.  **Lead Hunter**: Cross-domain synthesis, intelligence report generation, and iterative investigation (2 rounds)

**Intelligence Report Requirements:**
The Lead Hunter must produce a **comprehensive threat intelligence analysis**, not just a malware scan. The report must include:
*   **Executive Summary**: High-level threat overview and key findings
*   **Campaign Timeline**: Chronological evolution of threat infrastructure
*   **Attack Narrative**: Complete kill chain from delivery through post-exploitation
*   **Threat Profiling**: Attribution, sophistication assessment, campaign classification
*   **Infrastructure Mapping**: DNS/IP relationships, hosting patterns, shared infrastructure
*   **Malware Intelligence**: Capabilities, evasion techniques, code similarities, IOC expansion
*   **Attack Flow Diagram**: Visual representation of infrastructure and attack chain  (Graphviz)
*   **Intelligence Gaps**: Missing data, research pivots, recommended next steps
*   **Attribution & Context**: Campaign indicators, related threat actors, MITRE ATT&CK mapping
*   **IOC Summary**: High-confidence vs. low-confidence indicators for distribution

### 3.3 The Knowledge Graph
*   **Schema**: Hybrid (Fixed Layout Properties + Dynamic Intelligence Properties).
*   **Edges**: Automatic mapping from MCP response keys.
*   **Comprehensive Relationship Coverage (52 types)**:
    - **File IOCs (20 relationships)**: `associations`, `bundled_files`, `contacted_domains`, `contacted_ips`, `contacted_urls`, `dropped_files`, `embedded_domains`, `embedded_ips`, `embedded_urls`, `email_attachments`, `email_parents`, `execution_parents`, `itw_domains`, `itw_ips`, `itw_urls`, `malware_families`, `memory_pattern_domains`, `memory_pattern_ips`, `memory_pattern_urls`, `attack_techniques`
    - **Domain IOCs (14 relationships)**: `associations`, `caa_records`, `cname_records`, `communicating_files`, `downloaded_files`, `historical_ssl_certificates`, `immediate_parent`, `parent`, `referrer_files`, `resolutions`, `siblings`, `subdomains`, `urls`, `malware_families`
    - **IP IOCs (6 relationships)**: `communicating_files`, `downloaded_files`, `historical_whois`, `referrer_files`, `resolutions`, `urls`
    - **URL IOCs (12 relationships)**: `communicating_files`, `contacted_domains`, `contacted_ips`, `downloaded_files`, `embedded_js_files`, `last_serving_ip_address`, `memory_pattern_parents`, `network_location`, `redirecting_urls`, `redirects_to`, `referrer_files`, `referrer_urls`
*   **Graph Visualization Strategy**:
    - **Display**: IOC-to-IOC relationships (files, domains, IPs, URLs).
    - **Clustering**: Hierarchical clustering for high-volume nodes (e.g., "Contacted Domains").
    - **Smart Truncation**: Filenames are truncated (24 chars + ext) to preserve SHA256 hashes.
    - **Filtering**: Contextual metadata (`attack_techniques`, etc.) analyzed but not visualized.
    - **Capacity**: 15 entities per relationship, 150 total.
    
### 3.3.1 Data Flow Strategy (Memory Architecture)
*   **Dual-Layer Memory**:
    *   **Data Layer (NetworkX)**: Acts as the "Hard Drive". Stores **100% of fetched data** (full JSON attributes). Agents MUST write to this *first*.
    *   **Control Layer (LangGraph)**: Acts as the "RAM". Stores **token-optimized summaries** (<5% of data). Agents write to this *second*.
*   **Rule**: "Store First, Summarize Second". Agents never pass raw API JSON into the LangGraph state `messages` or `context` to prevent context window exhaustion.

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
