# Project Harimau

Cloud-Native AI Threat Hunter using LangGraph as the GraphRAG and Vertex AI as the LLM. 

This project was the outcome of the learnings from the ai_threathunter project, which made the decision to rebuild the entire logic on Google Cloud and LangGraph for threat hunting. 

## How it works

The application takes an IOC (like a file hash, URL, or IP address) and kicks off an investigation. Specialist AI Agents work together to analyze the IOC, gather threat intelligence, and produce a report with their findings.

The primary agents are:
- **Triage Specialist**: Performs the initial analysis of the IOC to determine its nature and threat level.
- **Malware Analysis Specialist**: Conducts a deep-dive behavioral analysis of file-based IOCs to understand their capabilities.
- **Infrastructure Analysis Specialist**: Maps out adversary infrastructure and finds connections between different network IOCs such as IP addresses and domains.

The agents use MCP tools to interact with threat intelligence sources like Google Threat Intelligence (GTI) to enrich their analysis. 

## Project Phases

### Phase 1: Cloud Run Microservices (Foundation)
*   Decomposed monolithic agent into **Backend** and **GTI MCP** services.
*   Implemented SSE (Server-Sent Events) for secure intra-service communication.
*   **Status**: Complete.

### Phase 2: Asynchronous & Persistent (Current)
*   **Status**: Verified Live.
*   Introduced **Cloud Tasks** for reliable job queuing.
*   Implemented **Cloud SQL (PostgreSQL)** for state persistence (`AsyncPostgresSaver`).
*   Robust error handling and "fail-fast" startup logic.
*   **Status**: Complete.

## Architecture (Phase 2)

The system uses an asynchronous, persistent architecture to handle long-running threat hunts:

1.  **API**: Cloud Run Service (Backend) receives `POST /investigate` requests.
2.  **Queue**: Enqueues jobs to **Google Cloud Tasks**.
3.  **Worker**: Cloud Tasks triggers the Worker endpoint on the same service.
4.  **Persistence**: **Cloud SQL (PostgreSQL)** stores Job Status and LangGraph Checkpoints (`AsyncPostgresSaver`).
5.  **Intelligence**: Queries an isolated **GTI MCP Server** (Sidecar/Service) for threat data.

## Future Roadmap

### Phase 3: Graph Foundation (The Brain)
- Integrate **KuzuDB** for embedded graph storage.
- Define flexible Schema (`IP`, `Hash`, `Behavior`).
- Enable Triage Agent to populate the graph dynamically.

### Phase 4: Specialist Swarm (The Team)
- **Malware Hunter**: Autonomous deep-dives on file hashes.
- **Infrastructure Hunter**: Pivoting on IPs and Domains.
- **Synthesis Agent**: Graph-RAG reporting using Gemini + KuzuDB.


## Setup

### 1. Prerequisites
- Google Cloud Project with Billing enabled.
- `gcloud` CLI installed and authenticated.
- **APIs Enabled**: Cloud Run, Cloud Build, Cloud SQL Admin, Cloud Tasks.

### 2. Infrastructure Setup
**Region**: `asia-southeast1` (Recommended)

```bash
# 1. Create Cloud SQL Instance (PostgreSQL)
gcloud sql instances create harimau-db --database-version=POSTGRES_15 --tier=db-f1-micro --region=asia-southeast1

# 2. Create Cloud Tasks Queue
gcloud tasks queues create investigation-queue --location=asia-southeast1

# 3. Create Secrets (GTI_API_KEY and DB_PASSWORD)
printf "your_api_key" | gcloud secrets create GTI_API_KEY --data-file=-
printf "your_db_password" | gcloud secrets create DB_PASSWORD --data-file=-
```

### 3. Environment Variables
Create a `.env` file (for local) or configure in Cloud Run:
- `GOOGLE_CLOUD_PROJECT`: Your Project ID
- `CLOUD_TASKS_QUEUE`: `investigation-queue`
- `CLOUD_TASKS_LOCATION`: `asia-southeast1`
- `DB_URL`: `postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance`
- `SERVICE_URL`: URL of the deployed Cloud Run service (required for Cloud Tasks callbacks)

### 4. Local Development
To run locally, you need **Cloud SQL Proxy**:

1.  Start Proxy:
    ```bash
    ./cloud-sql-proxy project:region:instance
    ```
2.  Run App:
    ```bash
    uvicorn backend.main:app --reload
    ```

### 5. Deployment
Deploy using Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml .
```

## API Reference

### 1. Start Investigation
**POST** `/investigate`
- **Body**: `{"ioc": "1.1.1.1"}`
- **Response**: `200 OK`
  ```json
  {
    "job_id": "inv-1234abcd",
    "status": "queued",
    "message": "Investigation started"
  }
  ```

### 2. Poll Status
**GET** `/investigations/{job_id}`
- **Response**: `200 OK`
  ```json
  {
    "id": "inv-1234abcd",
    "status": "completed",
    "result": { ... }
  }
  ```

### 3. Worker Callback (Internal)
**POST** `/internal/worker`
- **Description**: Target for Cloud Tasks. Protected by `X-CloudTasks-QueueName` (Prod) or OIDC.
- **Body**: `{"job_id": "...", "ioc": "..."}`

### 4. Health Check
**GET** `/health`
- **Response**: `{"status": "healthy"}`

