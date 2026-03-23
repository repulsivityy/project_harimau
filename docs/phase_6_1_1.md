# Phase 6.1.1 — Move `max_iterations` into `AgentState`

**Date**: 2026-03-23  
**Status**: Planned (pending Phase 6.1 deployment validation)  
**Prerequisite**: Phase 6.1 fixes deployed and validated on Cloud Run  
**Test Runner**: `python -m pytest tests/test_flow_logic.py tests/test_max_iterations.py -v`

---

## 1. Purpose

This change moves the hardcoded `max_iterations` / `hunt_iterations` constants into `AgentState`, allowing the user to configure investigation depth per-request from the frontend.

**Why it exists now**: Phase 6.1 discovered two separate constants controlling the same limit:
- `workflow.py` line 11: `hunt_iterations = 3` → used by `route_from_lead_hunter`
- `lead_hunter.py` line 43: `MAX_ITERATIONS = 3` → used by `lead_hunter_node`

They happen to be equal today, but are **not linked**. A drift would silently break the loop logic.

**Business motivation**: `max_iterations` controls **cost vs. investigative depth**. Exposing it to the user lets analysts choose between a fast cheap triage (`max_iterations=1`) and a deep thorough investigation (`max_iterations=5`).

---

## 2. Proposed Changes

### 2.1 Add env-var default in `backend/config.py` [NEW]

```python
import os

# Operator-level default: override via Cloud Run env var
# gcloud run services update harimau-backend --set-env-vars HUNT_ITERATIONS=5
DEFAULT_HUNT_ITERATIONS = int(os.getenv("HUNT_ITERATIONS", "3"))
```

This gives operators Cloud Run-level control without redeployment. User requests override this on a per-investigation basis.

---

### 2.2 Add `max_iterations` to `AgentState` (`backend/graph/state.py`)

```diff
+    # Investigation depth: controls cost vs. depth trade-off
+    # Set from POST /api/investigate, persists unchanged through entire loop
+    max_iterations: Annotated[int, last_value]
```

Uses `last_value` reducer — no agent writes to it, so the initial value persists unchanged through every loop iteration.

---

### 2.3 Add `max_iterations` to `InvestigationRequest` and `initial_state` (`backend/main.py`)

```diff
+from backend.config import DEFAULT_HUNT_ITERATIONS

 class InvestigationRequest(BaseModel):
     ioc: str
+    max_iterations: int = DEFAULT_HUNT_ITERATIONS

 initial_state = {
     ...
+    "max_iterations": request.max_iterations,
 }
```

> [!IMPORTANT]  
> `initial_state` must also be updated with a corresponding key (alongside Fix 3 changes).

---

### 2.4 Remove hardcoded constants, read from state (`backend/graph/workflow.py`)

```diff
-hunt_iterations = 3  # Remove module-level constant

 def route_from_lead_hunter(state: AgentState):
-    max_iterations = hunt_iterations
+    max_iterations = state.get("max_iterations", DEFAULT_HUNT_ITERATIONS)
     iteration = state.get("iteration", 0)
     ...
```

Import `DEFAULT_HUNT_ITERATIONS` from `backend.config` as fallback for safety.

---

### 2.5 Remove hardcoded constant, read from state (`backend/agents/lead_hunter.py`)

```diff
+from backend.config import DEFAULT_HUNT_ITERATIONS

 async def lead_hunter_node(state: AgentState):
-    MAX_ITERATIONS = 3
+    MAX_ITERATIONS = state.get("max_iterations", DEFAULT_HUNT_ITERATIONS)
```

---

### 2.6 Frontend — expose the control (Streamlit `app/`)

Add a sidebar slider or input field:

```python
max_iterations = st.slider(
    "Investigation Depth (iterations)",
    min_value=1,
    max_value=5,
    value=3,
    help="Higher = deeper pivots, higher cost. Lower = faster, cheaper."
)
```

Pass to backend:
```python
response = requests.post(
    f"{BACKEND_URL}/api/investigate",
    json={"ioc": ioc, "max_iterations": max_iterations}
)
```

---

## 3. Execution Flow After Change

```
User sets max_iterations=5 in frontend
         ↓
POST /api/investigate {"ioc": "...", "max_iterations": 5}
         ↓
initial_state["max_iterations"] = 5   ← set once, never overwritten
         ↓
LangGraph state carries it through every node
         ↓
lead_hunter_node reads state["max_iterations"]  → synthesis at iteration 5
route_from_lead_hunter reads state["max_iterations"] → hard stop at iteration > 5
         ↓
Both guards consistent — single source of truth ✅
```

---

## 4. Files to Change

| File | Change |
|---|---|
| `backend/config.py` | **[NEW]** `DEFAULT_HUNT_ITERATIONS` from env var |
| `backend/graph/state.py` | Add `max_iterations: Annotated[int, last_value]` |
| `backend/main.py` | Add field to `InvestigationRequest` + `initial_state` |
| `backend/graph/workflow.py` | Remove `hunt_iterations` constant, read from state |
| `backend/agents/lead_hunter.py` | Remove `MAX_ITERATIONS = 3`, read from state |
| `app/` (Streamlit frontend) | Add depth slider, pass to `POST /api/investigate` |

---

## 5. Unit Tests (`tests/test_max_iterations.py`)

All tests use mocks — no Cloud Run required.

| Test | What it verifies |
|---|---|
| `test_default_hunt_iterations_from_env` | `DEFAULT_HUNT_ITERATIONS` reads `HUNT_ITERATIONS` env var |
| `test_investigation_request_accepts_max_iterations` | `InvestigationRequest` accepts and defaults `max_iterations` |
| `test_initial_state_includes_max_iterations` | `initial_state` dict contains `max_iterations` key |
| `test_route_from_lead_hunter_reads_from_state` | Routing function respects `state["max_iterations"]`, not module var |
| `test_lead_hunter_synthesis_at_max_iterations` | Synthesis triggered when `iteration >= state["max_iterations"]` |
| `test_max_iterations_1_stops_early` | `max_iterations=1` stops after first lead_hunter pass |
| `test_max_iterations_5_allows_more_loops` | `max_iterations=5` routes back to `gate` at iteration 3 |

---

## 6. Cloud Run Deployment

No schema changes required — `max_iterations` is a request parameter, not stored in the DB permanently (it flows through LangGraph state only). The `investigations` table is unchanged.

**Operator default** (no redeployment for user changes):
```bash
gcloud run services update harimau-backend \
  --set-env-vars HUNT_ITERATIONS=3
```

**Per-request override**: user sets value in frontend UI — passed via `POST /api/investigate`.
