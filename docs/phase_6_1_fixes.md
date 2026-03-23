# Phase 6.1 — IOC Flow → CloudSQL Persistence Fixes

**Date**: 2026-03-23  
**Status**: ✅ Complete (6 of 6 fixes applied, 22 tests passing)  
**Test Runner**: `python -m pytest tests/test_flow_logic.py -v`  
**Constraint**: All unit tests use mocks — no Cloud Run / CloudSQL / API keys required locally.

---

## 1. Purpose

This document is a knowledge transfer for any agent continuing Phase 6.1 work. It captures:

- **Why** these fixes exist (the root problems in the persistence flow)
- **What** was changed (completed fixes with exact file/line references)
- **What remains** (4 pending fixes with proposed diffs)
- **How to verify** (unit test structure and commands)

### Background

Phase 6 of Project Harimau adds CloudSQL (PostgreSQL) persistence for investigations and LangGraph checkpointing. The investigation flow is:

```
POST /api/investigate
  → _run_investigation_background(job_id, ioc)
    → save_job(job_id, {status: "running"})        # Initial record
    → app_graph.ainvoke(initial_state, config)      # LangGraph workflow
      → triage_node → gate_node → specialists → lead_hunter → (loop or END)
    → save_job(job_id, result)                      # Final result
  → GET /api/investigations/{job_id}                # Consumer polls this
    → get_job(job_id)                               # Reads from CloudSQL or JOBS dict
```

A code review identified **6 logic issues** in this flow that can cause data loss, serialization failures, or silent bugs.

---

## 2. Architecture Context (for the continuing agent)

### Key Files

| File | Role |
|---|---|
| `backend/main.py` | FastAPI app, lifespan (DB + checkpointer init), `save_job`/`get_job`, `_run_investigation_background`, all API endpoints |
| `backend/graph/state.py` | `AgentState` TypedDict with custom reducers (`merge_dicts`, `last_value`, `merge_graphs`, `operator.add`) |
| `backend/graph/workflow.py` | LangGraph `StateGraph` definition: triage → gate → specialists → lead_hunter → loop. `create_graph(checkpointer=None)` |
| `backend/agents/triage.py` | Phase 1 (fetch GTI data → NetworkX cache) + Phase 2 (LLM analysis → subtasks). Sets `state["investigation_graph"]`, `state["iteration"]` |
| `backend/agents/lead_hunter.py` | Orchestrator: planning mode (generate new subtasks) or synthesis mode (final report). Uses `InvestigationCache(state.get("investigation_graph"))` |
| `backend/agents/lead_hunter_planning.py` | LLM-driven planning: reads graph, identifies uninvestigated nodes, generates subtasks |
| `backend/agents/lead_hunter_synthesis.py` | LLM-driven final report synthesis |
| `backend/utils/graph_cache.py` | `InvestigationCache` wrapping `nx.MultiDiGraph` with add/get/merge/export methods |
| `backend/utils/graph_formatter.py` | Formats graph data from `rich_intel` for the `/graph` endpoint |
| `backend/graph/sse_wrappers.py` | Decorator wrapping agent nodes with SSE event emissions |
| `tests/test_flow_logic.py` | **All Fix 1–6 unit tests go here** |
| `tests/test_persistence_shape.py` | Pre-existing tests for `save_job`/`get_job` round-trip shape consistency |

### AgentState Schema (`backend/graph/state.py`)

```python
class AgentState(TypedDict):
    job_id: Annotated[str, last_value]
    ioc: Annotated[str, last_value]
    ioc_type: Annotated[Optional[str], last_value]
    messages: Annotated[List[BaseMessage], operator.add]
    subtasks: Annotated[List[Dict[str, Any]], last_value]
    specialist_results: Annotated[Dict[str, Any], merge_dicts]
    final_report: Annotated[Optional[str], last_value]
    metadata: Annotated[Dict[str, Any], merge_dicts]
    investigation_graph: Annotated[Optional[Any], merge_graphs]  # nx.MultiDiGraph
    loop_count: Annotated[int, operator.add]
    iteration: Annotated[int, last_value]
    lead_plan: Optional[str]
    lead_hunter_report: Annotated[Optional[str], last_value]
```

### Persistence Design

- **CloudSQL (asyncpg)**: `save_job` INSERTs/UPSERTs into `investigations` table. Nested fields (`subtasks`, `rich_intel`, `specialist_results`, `transparency_log`) are packed into the `metadata` JSONB column on save, unpacked back to top-level on `get_job`.
- **In-memory fallback**: `JOBS = {}` dict used when `db_pool` is `None` or DB write fails.
- **LangGraph Checkpointer**: `AsyncPostgresSaver` (psycopg-based) persists LangGraph state snapshots at each node transition. Separate from the `asyncpg` pool.

### Dependencies (`backend/requirements.txt`)

Already includes: `asyncpg`, `psycopg[binary]`, `langgraph-checkpoint-postgres`, `langgraph`, `networkx`

---

## 3. Completed Fixes

### Fix 1: Strip `investigation_graph` from `save_job` result ✅

**Problem**: `_run_investigation_background` built a `result` dict containing `"investigation_graph": final_state.get("investigation_graph")` — a `nx.MultiDiGraph` object. This is not JSON-serializable. When `save_job` calls `json.dumps(metadata)`, it would either crash or silently fall back to in-memory `JOBS`.

**Root cause**: Line 340 of `main.py` (pre-fix) included the NetworkX graph in the result.

**Fix applied** (`backend/main.py` line 340–341):
```diff
-            "investigation_graph": final_state.get("investigation_graph"),  # Add graph to result
+            # NOTE: investigation_graph (NetworkX object) intentionally excluded — not JSON-serializable.
+            # Graph data is served via /api/investigations/{job_id}/graph using rich_intel.
```

**Why this is safe**: The `/api/investigations/{job_id}/graph` endpoint uses `rich_intel` (from `metadata` JSONB), not `investigation_graph`. The NetworkX graph only lives in-memory during the LangGraph execution.

**Tests** (3 tests in `TestFix1InvestigationGraphExcluded`):
- `test_result_does_not_contain_investigation_graph` — result dict has no `investigation_graph` key
- `test_result_serializable_to_json` — `json.dumps(result)` succeeds
- `test_result_survives_db_round_trip` — save → get round-trip works

---

### Fix 2: Wire LangGraph checkpointer to CloudSQL ✅

**Problem**: `create_graph()` in `workflow.py` accepts a `checkpointer` parameter and passes it to `workflow.compile(checkpointer=checkpointer)`, but `main.py` always called `create_graph()` without one — meaning LangGraph never persisted state snapshots to CloudSQL.

**Fix applied** (`backend/main.py` lifespan function):

1. **New global**: `checkpointer_instance = None`

2. **Startup** (inside the `db_url` success path):
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
checkpointer_ctx = AsyncPostgresSaver.from_conn_string(db_url)
checkpointer_instance = await checkpointer_ctx.__aenter__()
await checkpointer_instance.setup()  # Creates checkpoint tables
app_graph = create_graph(checkpointer=checkpointer_instance)
```

3. **Fallback**: If checkpointer init fails, logs error and calls `create_graph()` without it.

4. **Shutdown**: Closes checkpointer via `await checkpointer_ctx.__aexit__(None, None, None)` before closing `asyncpg` pool.

**Key detail**: `AsyncPostgresSaver` uses `psycopg` (not `asyncpg`). This is a separate connection from the `asyncpg` pool used by `save_job`/`get_job`. Both connect to the same `DATABASE_URL`.

**Tests** (4 tests in `TestFix2CheckpointerWiring`):
- `test_create_graph_accepts_checkpointer_param` — AST-parses `workflow.py` to verify function signature
- `test_create_graph_passes_checkpointer_to_compile` — AST-parses to verify `workflow.compile(checkpointer=...)` call
- `test_lifespan_wiring_creates_checkpointer_when_db_available` — source-level check for `AsyncPostgresSaver` usage + `create_graph(checkpointer=...)` + fallback `create_graph()`
- `test_lifespan_shutdown_closes_checkpointer` — verifies `checkpointer_instance` tracking and `__aexit__` cleanup

---

### Fix 3: `initial_state` missing required `AgentState` fields ✅

**Problem**: `_run_investigation_background` created `initial_state` without `iteration`, `loop_count`, or `investigation_graph`. These are required by `AgentState`:
- `iteration` — `lead_hunter.py` reads `state.get("iteration", 0)` and `triage.py` sets it to `1`. The `last_value` reducer needs an initial value.
- `loop_count` — uses `operator.add` reducer which requires an initial `int`.
- `investigation_graph` — `InvestigationCache(state.get("investigation_graph"))` in triage expects this key.

**Fix applied** (`backend/main.py` lines 243–252):
```diff
 initial_state = {
     "job_id": job_id,
     "ioc": ioc,
     "messages": [],
     "subtasks": [],
     "specialist_results": {},
-    "metadata": {}
+    "metadata": {},
+    "iteration": 0,
+    "loop_count": 0,
+    "investigation_graph": None
 }
```

**Why this is safe**: `triage.py` overwrites `iteration` to `1` on its first run. `lead_hunter.py` uses `.get("iteration", 0)` defensively. `InvestigationCache` already handles `None` as the initial graph (creates a fresh `MultiDiGraph`). Setting `loop_count: 0` satisfies the `operator.add` reducer which accumulates across nodes.

**Tests** (5 tests in `TestFix3InitialState`):
- `test_initial_state_has_iteration` — AST-verified key presence
- `test_initial_state_has_loop_count` — AST-verified key presence
- `test_initial_state_has_investigation_graph` — AST-verified key presence
- `test_initial_state_has_all_core_fields` — all 9 required fields present
- `test_initial_state_correct_defaults` — types match reducer expectations (`int`, `list`, `dict`, `None`)

---

### Fix 4: `save_job` silent fallback — enhance error logging ✅

**Problem**: When `save_job`'s DB write failed (e.g. `json.dumps(metadata)` on a non-serializable value), the error log was generic — no indication of which keys caused the failure. Data silently fell back to in-memory `JOBS`.

**Fix applied** (`backend/main.py` lines 161–165):
```diff
  except Exception as e:
-     logger.error("save_job_db_failed", job_id=job_id, error=str(e))
+     logger.error("save_job_db_failed", job_id=job_id, error=str(e),
+                  data_keys=list(data.keys()),
+                  metadata_keys=list(metadata.keys()) if 'metadata' in dir() else "N/A")
      JOBS[job_id] = data
```

**Why this matters**: In Cloud Logging, the `data_keys` and `metadata_keys` fields immediately show which fields were being serialized when the error occurred — turning a cryptic `TypeError` into an actionable debug trace.

**Tests** (3 tests in `TestFix4SaveJobErrorLogging`):
- `test_save_job_falls_back_to_jobs_on_db_error` — DB write raises → data saved to in-memory JOBS
- `test_save_job_error_produces_debuggable_info` — replicated packing logic captures correct keys
- `test_source_contains_enhanced_error_logging` — source-level check for `data_keys` and `metadata_keys`

---

### Fix 5: `get_job` returns stale in-memory data on DB error ✅

**Problem**: If `db_pool` existed but the DB query failed, `get_job` fell back to `JOBS.get(job_id)` which could contain stale data (e.g. `"running"` status while DB actually held `"completed"`). This created a split-brain between the two data sources.

**Fix applied** (`backend/main.py` line 198):
```diff
  except Exception as e:
      logger.error("get_job_db_failed", job_id=job_id, error=str(e))
-     return JOBS.get(job_id)
+     return None  # Don't serve stale in-memory data when DB is the source of truth
```

**Why this is safe**: When `db_pool` is `None` (no DB configured), the final `return JOBS.get(job_id)` at the end of `get_job` still works — that path is unchanged. The fix only affects the `except` block when DB *is* configured but a query fails. Callers already handle `None` returns (the status endpoint returns 404).

**Tests** (3 tests in `TestFix5GetJobNoStaleFallback`):
- `test_get_job_returns_none_on_db_error` — DB raises → returns `None`, not stale JOBS data
- `test_get_job_still_uses_jobs_when_no_db_pool` — no DB configured → JOBS fallback still works
- `test_source_get_job_error_returns_none` — source-level check for the Fix 5 comment

---

### Fix 6: Error handler in `_run_investigation_background` fails when no prior job exists ✅

**Problem**: If `_run_investigation_background` threw and `get_job(job_id)` returned `None` (because the initial `save_job("running")` also failed), the error was swallowed — the job was never marked `"failed"` anywhere.

**Fix applied** (`backend/main.py` lines 379–389):
```diff
    except Exception as e:
        logger.error("investigation_failed", job_id=job_id, error=str(e))
        job = await get_job(job_id)
-       if job:
-           job["status"] = "failed"
-           if "metadata" not in job or not isinstance(job["metadata"], dict):
-               job["metadata"] = {}
-           job["metadata"]["error"] = f"Investigation Failed: {str(e)}"
-           await save_job(job_id, job)
+       if not job:
+           job = {"job_id": job_id, "status": "failed", "ioc": ioc, "metadata": {}}
+       job["status"] = "failed"
+       if "metadata" not in job or not isinstance(job["metadata"], dict):
+           job["metadata"] = {}
+       job["metadata"]["error"] = f"Investigation Failed: {str(e)}"
+       await save_job(job_id, job)
```

**Why this is safe**: The `ioc` variable is in scope (parameter of `_run_investigation_background`). The minimal record `{job_id, status, ioc, metadata}` satisfies `save_job`'s INSERT — other columns (`ioc_type`, `risk_level`, etc.) will be NULL which is acceptable for a failed investigation. When `get_job` does return an existing job, the original code path (update in-place + save) still runs.

**Tests** (4 tests in `TestFix6ErrorHandlerAlwaysPersists`):
- `test_creates_failure_record_when_get_job_returns_none` — None → minimal failure record created
- `test_preserves_existing_job_when_get_job_succeeds` — existing job updated in-place, fields preserved
- `test_error_handler_always_calls_save_job` — save_job called regardless of get_job result
- `test_source_error_handler_has_none_guard` — source contains `if not job:` guard

---

## 5. Test File Structure

All tests live in `tests/test_flow_logic.py`. The file has:

1. **Shared fixtures** (lines 15–58): `FakeConnection`, `FakePool`, `FakeAcquireContext` — simulates asyncpg connection/pool using an in-memory dict.
2. **Replicated helpers** (lines 63–115): `save_job()` and `get_job()` — extracted from `main.py` with injected `db_pool` and `JOBS` params (avoids importing FastAPI app).
3. **Test classes**: One per fix (e.g. `TestFix1InvestigationGraphExcluded`, `TestFix2CheckpointerWiring`).

**Important**: All `open()` calls reading source files must use `encoding="utf-8"` (Windows CRLF files cause `UnicodeDecodeError` otherwise).

Existing pre-Fix tests in `tests/test_persistence_shape.py` cover save/get round-trip shape consistency (9 tests). These should still pass and are complementary.

### Running Tests

```bash
# All flow logic tests
python -m pytest tests/test_flow_logic.py -v

# All tests (including pre-existing shape tests)
python -m pytest tests/ -v

# Specific fix
python -m pytest tests/test_flow_logic.py::TestFix3InitialState -v
```

---

## 6. Post-Fix Verification (on Cloud Run)

After all 6 fixes are implemented and local tests pass:

1. Deploy backend to Cloud Run: `./deploy.sh backend`
2. Submit investigation: `POST /api/investigate {"ioc": "185.220.101.188"}`
3. Verify:
   - Job persisted in CloudSQL `investigations` table
   - No `investigation_graph` key in `GET /api/investigations/{job_id}` response
   - `/api/investigations/{job_id}/graph` still works (uses `rich_intel`)
   - LangGraph checkpoint tables exist in CloudSQL (created by `checkpointer.setup()`)
   - Failed investigations have `status="failed"` in CloudSQL (not silently lost)

---

## 7. Related Documents

| Document | Path | Purpose |
|---|---|---|
| Architecture | `docs/architecture.md` | Full system architecture, data flow, roadmap |
| Agent Implementation | `docs/agent_implementation.md` | Agent strategy, prompts, tool usage |
| PRD | `docs/PRD.md` | Product requirements |
| AGENTS.MD | `AGENTS.MD` (root) | Core architecture rules for AI agents |
| Previous fix session | Conversation `6493ade1` | Earlier persistence shape fix work |

---

## 8. Key Decisions & Rationale

1. **Two DB connections**: `asyncpg` pool for `save_job`/`get_job` (app persistence) + `psycopg` connection for `AsyncPostgresSaver` (LangGraph checkpointing). Both use same `DATABASE_URL`. This is because LangGraph's checkpointer requires `psycopg`, not `asyncpg`.

2. **Graph not persisted to DB**: `investigation_graph` (NetworkX) stays in-memory during execution. The visualization endpoint uses `rich_intel` data instead. NetworkX persistence to DB is deferred to Phase 7 (FalkorDB).

3. **Fallback strategy**: Every DB operation has a fallback — checkpointer init failure → no checkpointer, `save_job` failure → in-memory JOBS, etc. This ensures the backend always starts, even if CloudSQL is unreachable.

4. **Test approach**: Since we can't install cloud dependencies locally (Vertex AI, MCP, networkx, etc.), tests use AST parsing of source files and mock objects instead of importing actual modules.
