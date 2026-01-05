# Project Harimau - Development Progress

## Session Date: January 6, 2026 (Final Phase 1 Deployment)

This document tracks the specific changes specific changes made during this development session.

---

## Changes Made

### 1. Fixed GTI Server Configuration
**File**: `mcp-servers/gti-server/gti_mcp/server.py`
**Changes**:
- **Standardized Env Var**: Renamed `VT_APIKEY` to `GTI_API_KEY` for consistency.
- **Fixed Secret Injection**: Added `.strip()` to API key handling to fix `ValueError: Newline or carriage return detected`.
- **Logging**: Switched to `logging.info` and set level to INFO.

### 2. Fixed MCP Registry (Backend)
**File**: `backend/tools/mcp_registry.py`
**Changes**:
- **Standardized Env Var**: Updated STDIO mode to use `GTI_API_KEY`.
- **Code Quality**: Removed unused imports, added Type Hints, fixed bare `except` clause.

### 3. Deployment Pipeline
**File**: `cloudbuild.yaml`
**Changes**:
- **Secret Injection**: Added `--set-secrets=GTI_API_KEY=GTI_API_KEY:latest` to GTI server deployment.
- **Env Mapping**: Mapped `GTI_API_KEY` secret to `GTI_API_KEY` env var.

---

## Validation Results

### 1. Deployment Verification
**Script**: `verify_deploy.py`
**Result**: **SUCCESS**

**Output**:
```json
{
    "status": "complete",
    "verdict": "BENIGN",
    "graph_size": 1,
    "findings": [
        {
            "agent": "triage",
            "verdict": "BENIGN",
            "decision": "Skip to Synthesis (benign IOC)"
        }
    ]
}
```

### 2. End-to-End Flow
- Backend received request via `POST /investigate`.
- Backend orchestrated Triage Agent via LangGraph.
- Triage Agent called `gti/get_domain_report` via `MCPRegistry` (SSE).
- GTI Server received request, queried VirusTotal API (using Sanitized Secret).
- Result returned to Backend -> Triage -> Response.

---

## Status
**Phase 1**: **COMPLETE**
**Current State**: Live on Cloud Run (US-Central1)
**Next Step**: Phase 2 (Asynchronous Job Queue)
