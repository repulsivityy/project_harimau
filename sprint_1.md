# Sprint 1 — Consolidated Execution Plan

> **Owner:** project_harimau · **Updated:** 2026-05-28 · **Status:** 🚧 In Progress
> **Pick-up agent:** Read this file top-to-bottom. Tasks are tiered by impact; complete Tier 1 before Tier 2 before Tier 3 before Tier 4. Within a tier, tasks are independent unless a dependency is called out.
> **Execution model:** This project runs **only on Google Cloud Run**. There is no local execution step. All verification is via deploy → hit deployed endpoint → inspect Cloud SQL state → user-driven browser check for UI. Do not add steps that require `npm run dev`, `uvicorn`, `docker-compose`, or local fixture runs.
> **Ground truth:** All findings in this file were verified against the **current code**, not the docs. Where docs and code drift, the code wins for execution; flag the drift and update `docs/CHANGELOG.md` + `docs/implementation_plan_v2.md`.
> **Plan before acting:** When you are about to perform an action, use a separate plan step to walk through with the user before execution. Always verify that your understanding is correct before proceeding. Always ground your plan in the code and docs, not in your own assumptions. 
> **Review once more after completion:** Review all the changes in the context of the code changed and the logic flow, before confirming with the user that it's all working. 
**DO NOT EXECUTE BEFORE USER APPROVAL.**

---

## §0 · Foundation (do before Tier 1)

| Step | Detail |
|---|---|
| **0.1 Branch + commit hygiene** | Create branch `sprint-1`. One commit per task ID. Subject format `feat(s1-<tier>-T<N>): <one-liner>`. One rollup PR per tier. |
| **0.2 Test scaffold** | Scaffold `backend/tests/` with `pytest.ini`, `conftest.py`, and a smoke `test_state_reducers.py`. Wire `pytest backend/tests` into `cloudbuild-backend.yaml` as a build step before the deploy step so test failures block deploys. |
| **0.3 Baseline metrics** | Run the §7 fixture against the **current Cloud Run deployment** (no code change). Capture `final_report` length, "Key Indicators" row count, persisted-graph node count with non-null `threat_score`, edge count, wall-clock. Store in `sprint_baselines/sprint_1_baseline.md` committed to the branch. Every Verify step compares against this. |
| **0.4 Housekeeping** | Delete `triage.py.bak`. Confirm `backend/agents/lead_hunter.py` is the **active orchestrator** (it calls `run_planning_phase` + `generate_final_report_llm`; do not delete). Document this in a one-line comment at top of `lead_hunter.py`. |
| **0.5 Doc drift policy** | When code contradicts `docs/`, the code wins. Flag the drift in the PR description and append a line to `docs/CHANGELOG.md`. Never edit `docs/implementation_plan_v2.md` to *remove* tasks — only tick them per `docs/FRAMEWORK.md`. |

---

# TIER 1 — Hunt Accuracy & Safety (Phase 1) [COMPLETED]

**Goal:** Every multi-pivot hunt produces a measurably more grounded synthesis report. Fix fragile parsing and threshold errors.

### [x] S1-T1 · Cross-agent peer findings into specialist prompts
*   **Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`, `backend/agents/lead_hunter_planning.py`
*   **Change:** Inject `infrastructure` findings into the `malware` agent's prompt (and vice versa) to enable true cross-agent deduction. Expand planner dedup logic to union both specialists' lists. Log `peer_findings_injected`.

### [x] S1-T2 · GTI attribute propagation + synthesis selector relaxation
*   **Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`, `backend/utils/graph_cache.py`, `backend/agents/lead_hunter_synthesis.py`
*   **Change:** Add helper `extract_gti_summary` in `graph_cache.py`. Read `threat_score` directly from GTI assessment and merge into cache node attributes. Relax synthesis gate in `lead_hunter_synthesis.py` so high-scoring items or specialist-discovered items surface cleanly.

### [x] S1-T3 · Strict Indicator parser regex + JSON `raw_text` fallback
*   **Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`, `backend/agents/triage.py`, `backend/utils/agent_utils.py`
*   **Change:** Replace fragile `if/elif` string matching (`"http" in ioc`, `"/" in ioc`) with rigorous ordered regex patterns (`^(?P<type>IP|Domain|URL|File|Hash)\s*:\s*(?P<value>.+)$`). In `parse_llm_json()`, fallback to saving `raw_text` on failure so synthesis has data.

### [x] S1-T4 · Triage signal threshold inclusive
*   **Files:** `backend/agents/triage.py`
*   **Change:** Fix off-by-one error dropping high-value pivots: change `> SIGNAL_MALICIOUS_VENDORS` to `>=`.

### [x] S1-T5 · Error Recovery Guard
*   **Files:** `backend/agents/lead_hunter_synthesis.py`, `backend/graph/workflow.py`
*   **Change:** Add a pre-synthesis check: if all specialist results return `System Error`, gracefully skip synthesis and return a structured error state instead of hallucinating a report.

---

# TIER 2 — State Machine & Cache Integrity (Phase 2)

**Goal:** Eliminate silent data loss in the persistence layer. Lower visibility, but reduces future bug surface and unlocks graph-query work.

### S2-T1 · State cleanup + `tasked_entities` reducer
*   **Files:** `backend/graph/state.py`, `backend/main.py`, `backend/agents/lead_hunter.py`
*   **Change:** Prune dead state fields (`concat_reports`, `loop_count`, `lead_plan`). Replace `tasked_entities` `operator.add` reducer with a proper `union_lists(a, b)` reducer to prevent exponential duplication.

### S2-T2 · MultiDiGraph merge: list-union node attrs + edge dedup
*   **Files:** `backend/graph/state.py`, `backend/utils/graph_cache.py`
*   **Change:** Implement proper deep-merge for node attributes in `state.py`. Guard `graph_cache.add_relationship` with edge deduplication logic to prevent parallel bloat.

### S2-T3 · Entity-ID normalisation
*   **Files:** `backend/utils/graph_cache.py`, `backend/main.py`
*   **Change:** Create `_normalise_id` helper (lowercase, whitespace stripping, IP formatting). Apply to cache operations and initial `state["ioc"]` on intake.

---

# TIER 3 — Frontend Stability & Interactivity (Phase 3)

**Goal:** High-impact UX improvements and structural ReactFlow fixes.

### S3-T1 · ReactFlow Simulation Fixes
*   **Files:** `app/src/app/investigate/[id]/page.tsx`
*   **Change:** Move `d3-force` simulation outside of the `setNodes` state updater. Add `requestAnimationFrame` throttling for ticks. Add `nodeOrigin={[0.5, 0.5]}` to fix visual misalignment. Handle drag pinning and cleanup on unmount.

### S3-T2 · Graph legend & Threat-score gradient
*   **Files:** `app/src/app/investigate/[id]/page.tsx` (CustomNode)
*   **Change:** Add a collapsible legend panel. Replace binary malicious border with a fill gradient on nodes (`threat_score < 40` → green, `40-70` → amber, `≥70` → red).

### S3-T3 · Focus mode (2-hop dim) & Node Detail Panel
*   **Files:** `app/src/app/investigate/[id]/page.tsx`
*   **Change:** Add "Focus" toggle to dim nodes >2 hops away. Finalize slide-in detail panel to show vendor detections, relationships, and add a "Recenter" button.

---

# TIER 4 — LangGraph Architecture Refactoring (Phase 4)

**Goal:** Fix structural debt. Run after Tiers 1-3 ship and soak.

### S4-T1 · Strict structured output
*   **Files:** `backend/agents/*.py`
*   **Change:** Migrate JSON outputs from string-parsing to LangChain `with_structured_output()` using Pydantic schemas.

### S4-T2 · Native LangGraph `ToolNode` for specialists
*   **Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`
*   **Change:** Rip out the internal `while/for` loops inside the specialists. Replace with native LangGraph `ToolNode`s and conditional edges. Unlocks per-step checkpointing.

### S4-T3 · Deterministic Graphviz
*   **Files:** `backend/agents/lead_hunter_synthesis.py`
*   **Change:** Generate the base DOT template directly from the `NetworkX` cache. Pass it as a structured template to the LLM for annotation to eliminate structural hallucinations.

### S4-T4 · SSE error wrapping & dynamic progress
*   **Files:** `backend/graph/sse_wrappers.py`
*   **Change:** Wrap `emit_event` in try/except. Make progress curves dynamically driven by `len(state["subtasks"]) * current_iteration`.

### S4-T5 · Synthesis quality
*   **Files:** `backend/agents/lead_hunter_synthesis.py`
*   **Change:** Pass complete edge attributes (`source_type`, `target_verdict`, `rel_type`) into the synthesis context so LLM names relationships accurately.

---

## §6 · Canonical test fixture

For every Verify step, hunt the same two IOCs against the deployed Cloud Run backend:

1. **A multi-pivot file hash** — start with `44d88612fea8a8f36de82e1278abb02f` (PRD example).
2. **A C2 domain** flagged malicious in GTI with ≥5 communicating files.

Per-task metrics captured (compared against `sprint_baselines/sprint_1_baseline.md`):
- `final_report` markdown length & "Key Indicators" row count
- Persisted-graph nodes with non-null `threat_score`
- Edge count (must not double after S2-T2)
- Hunt total wall-clock (must not regress >20%)

---

## §7 · Handoff notes

- **Memory:** `feedback_agent_prompts` (don't derive `threat_score`, don't touch Shodan prompt section) and `feedback_working_style` (propose before implementing; commit messages short one-liners).
- **Order:** Tier 1 → Tier 2 → Tier 3 → Tier 4. Within Tier 1: T1 + T2 first (largest accuracy gain, independent), then T3/T4 in parallel. Tier 3 T2 depends on Tier 1 T2 being deployed.
- **Per FRAMEWORK.md:** tick `docs/implementation_plan_v2.md` as you go (`[/]` → `[x]` with date). Append Challenges & Learnings notes for non-obvious findings.
- **Commit hygiene:** one commit per task ID, subject `feat(s1-<tier>-T<N>): …`. One rollup PR per tier.
- **No local runs.** All verification is Cloud Run deploy → endpoint hit → Cloud SQL inspection → user-driven browser check.
- **If blocked:** add `### Blocker — <task>` at bottom of this file and stop — do not silently proceed past the blocker.
