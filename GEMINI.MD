# Instructions [Project Harimau V2]

## Project Purpose
To build a cloud-native, AI-driven threat hunting platform that leverages **LangGraph** for orchestration and **FalkorDB** for graph-based state management.

## Core Architecture Rules
1.  **Micro-Modular Architecture**:
    *   **Backend (`/backend`)**: FastAPI + LangGraph. Handles state, agents, and Cloud Tasks webhooks.
    *   **Frontend (`/app`)**: Streamlit. Pure UI, communicates with Backend via API.
2.  **MCP Strategy**:
    *   **Deployment**: Embedded within the Backend container (Monolith).
    *   **Transport**: `stdio` (Standard Input/Output) for zero-latency local communication.
    *   **Source**: Reuse official GTI server from `elevate_2025`.
3.  **Orchestrator**: LangGraph. Enforce `MAX_DEPTH` for recursion control.
4.  **Graph Database**: FalkorDB (Ephemeral Sidecar).
5.  **Compute**: Google Cloud Run (Serverless).
6.  **Deployment**: Selective updates via `deploy.sh` (Backend/Frontend/All).

## Agent Strategy
*   **Tiered Models**: Gemini 3.0 Flash (Triage) vs Gemini 3.0 Pro (Analysis).
*   **Config-Driven**: Define agent behaviors in `agents.yaml`.
*   **Tool Registry**: Load tools dynamically via `mcp_registry.json`.

## Graph Schema Strategy
*   **Nodes**: Hybrid Schema (Core UI props + Dynamic Agent props).
*   **Edges**: "GTI-First" (Map API keys to Edge names automatically).
*   **Librarian**: Async "Meta-Agent" to clean up schema messiness later (Human-in-the-Loop).

## Roadmap & Reliability
*   **Authentication**: Polling (MVP) -> SSE (Phase 5).
*   **Resiliency**: LangGraph Checkpointing (Phase 5) to handle Cloud Run crashes.
