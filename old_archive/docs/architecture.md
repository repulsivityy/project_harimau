# System Architecture

## Phase 1: Cloud Run Microservices

The following diagram illustrates the deployment architecture of the Project Harimau Triage Agent on Google Cloud Platform.

```mermaid
graph TD
    Client[Client / CLI] -- HTTPS POST /investigate --> Backend[Cloud Run: harimau-backend]
    
    subgraph "Google Cloud Platform"
        Backend -- HTTP/SSE --> GTI[Cloud Run: harimau-gti-mcp]
        Backend -- "Read API Key" --> Secrets[Secret Manager]
        
        GTI -- "Threat Intel API" --> VirusTotal[Google Threat Intelligence]
    end
    
    subgraph "Container Image Storage"
        GCR[Google Container Registry]
        GCR -.-> Backend
        GCR -.-> GTI
    end
    
    classDef service fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef cloud fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    
    class Backend,GTI service;
    class Secrets,GCR cloud;
```

## Component Interaction

1.  **Client**: Initiates investigation via `POST /investigate` with an IOC (e.g., `google.com`).
2.  **Harimau Backend**:
    *   Authenticates via IAM (if enabled) or public endpoint for Phase 1.
    *   Initializes the **LangGraph** workflow.
    *   **Triage Agent** routes requests to the **MCP Registry**.
3.  **MCP Registry**:
    *   Retrieves the `GTI_MCP_URL` from environment variables.
    *   Establishes an **SSE (Server-Sent Events)** connection to the GTI MCP Service.
    *   Sends JSON-RPC requests to querying tools (`get_domain_report`, etc.).
4.  **Harimau GTI MCP**:
    *   Receives MCP requests.
    *   Authenticates with **Google Threat Intelligence** using the key stored in Secret Manager (injected as env var).
    *   Returns threat data to the Backend.
5.  **Synthesis Agent**:
    *   Aggregates findings.
    *   Generates the final Markdown report.

## Phase 2: Asynchronous & Persistent (Current)

This phase introduces reliability and state persistence using Cloud SQL and Cloud Tasks.

```mermaid
graph TD
    Client[Client / CLI] -- POST /investigate --> API[Cloud Run: Backend API]
    API -- Enqueue Job --> Tasks[Cloud Tasks Queue]
    API -- Create Job Record --> DB[(Cloud SQL: PostgreSQL)]
    
    subgraph "Async Execution"
        Tasks -- POST /internal/worker --> Worker[Cloud Run: Backend Worker]
        Worker -- Load/Save State --> DB
        Worker -- HTTP/SSE --> GTI[Cloud Run: GTI MCP]
    end
    
    Client -- GET /investigation/{id} --> API
    API -- Read Status --> DB
    
    GTI -- Threat Intel API --> VT[Google Threat Intelligence]
    
    classDef service fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef storage fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef queue fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    
    class API,Worker,GTI service;
    class DB storage;
    class Tasks queue;
```

### New Components

1.  **Cloud SQL (PostgreSQL)**:
    *   Stores `investigation_jobs` (Job ID, Status, Result).
    *   Stores **LangGraph Checkpoints** (Thread state) via `AsyncPostgresSaver`.
2.  **Cloud Tasks**:
    *   Decouples request submission from processing.
    *   Retries failed investigations automatically (configurable).
3.  **Worker Endpoint**:
    *   Private endpoint (`/internal/worker`) triggered only by Cloud Tasks.
    *   Executes the heavy Triage/Synthesis workflow.
