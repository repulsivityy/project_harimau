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

# TIER 2 — State Machine & Cache Integrity (Phase 2) [COMPLETED]

**Goal:** Eliminate silent data loss in the persistence layer. Lower visibility, but reduces future bug surface and unlocks graph-query work.

### [x] S2-T1 · State cleanup + `tasked_entities` reducer
*   **Files:** `backend/graph/state.py`, `backend/main.py`, `backend/agents/lead_hunter.py`
*   **Change:** Prune dead state fields (`concat_reports`, `loop_count`, `lead_plan`). Replace `tasked_entities` `operator.add` reducer with a proper `union_lists(a, b)` reducer to prevent exponential duplication.

### [x] S2-T2 · MultiDiGraph merge: list-union node attrs + edge dedup
*   **Files:** `backend/graph/state.py`, `backend/utils/graph_cache.py`
*   **Change:** Implement proper deep-merge for node attributes in `state.py`. Guard `graph_cache.add_relationship` with edge deduplication logic to prevent parallel bloat.

### [x] S2-T3 · Entity-ID normalisation
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

# TIER 4 — LangGraph Architecture Refactoring (Phase 4) [COMPLETED]

**Goal:** Fix structural debt. Run after Tiers 1-3 ship and soak.

### [x] S4-T1 · Strict structured output
*   **Files:** `backend/agents/*.py`
*   **Change:** Migrate JSON outputs from string-parsing to LangChain `with_structured_output()` using Pydantic schemas.

### [x] S4-T2 · Native LangGraph `ToolNode` for specialists
*   **Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`, `backend/utils/agent_utils.py`
*   **Change:** Rip out the internal `while/for` loops inside the specialists. Replace with native LangGraph `ToolNode`s and conditional edges. Unlocks per-step checkpointing.
*   **Note (2026-07-29):** The sub-graph refactor itself shipped on `main` in `9c3327f` + `a976cef` (2026-06-04) but was never ticked here. This tier closed the four gaps it left behind: restored the per-tool 20s timeout and catch-all that `run_tools_parallel` used to enforce (`ToolNode`'s default `handle_tool_errors` only converts `ToolInvocationError` and re-raises everything else); deleted the dead `run_tools_parallel` / `cap_context_window` code; hardened `route_after_agent` against non-`AIMessage` last messages; hoisted both routers to module scope so they are testable.

### [x] S4-T3 · Deterministic Graphviz
*   **Files:** `backend/utils/dot_builder.py` (new), `backend/agents/lead_hunter_synthesis.py`
*   **Change:** Generate the base DOT template directly from the `NetworkX` cache. Pass it as a structured template to the LLM for annotation to eliminate structural hallucinations.
*   **Note (2026-07-29):** Added a validation step with a deterministic fallback, because the frontend's `d3-graphviz` `renderDot()` is worker-based — its surrounding `try/catch` never fires, so malformed DOT rendered a blank panel with no error. The skeleton is keyed on real (normalised) entity ids rather than `_node_label()` display names, which previously let two distinct entities collapse into one DOT node. `_select_diagram_edges` is now the single edge selection shared by the diagram and the prose edge list.

### [x] S4-T4 · SSE error wrapping & dynamic progress
*   **Files:** `backend/utils/sse_manager.py`, `backend/graph/sse_wrappers.py`, `backend/utils/transparency.py`
*   **Change:** Wrap `emit_event` in try/except. Make progress curves dynamically driven by `len(state["subtasks"]) * current_iteration`.
*   **Note (2026-07-30):** Guarded at the source (`emit_event` itself) as well as in `with_sse_events` and the three `transparency.py` helpers, which are awaited from inside `@tool` bodies. Two concrete progress bugs fixed alongside: `triage` returned 10 for both `started` and `completed` (dead ternary), and the band was divided by `max_iterations` when there are actually `max_iterations + 1` specialist passes — specialists at `iteration == max_iterations` computed **103%**, clamped only client-side. Monotonicity is now enforced centrally by a per-job clamp in `sse_manager`, so it also covers the hardcoded percentages emitted from `main.py`.
*   **Correction:** the disconnect race this was written to prevent is not reachable today — `asyncio.Queue.put` on an unbounded queue never suspends, so the broadcast loop is atomic. The real pre-existing bug the snapshot fixes is a *silent drop* (a disconnecting client mutating the list mid-iteration caused later subscribers to be skipped, 1 of 3 delivered), not an exception. The guards remain as insurance for the day the queue gains a `maxsize`.

### [x] S4-T5 · Synthesis quality
*   **Files:** `backend/agents/lead_hunter_synthesis.py`, `backend/utils/dot_builder.py`
*   **Change:** Pass complete edge attributes (`source_type`, `target_verdict`, `rel_type`) into the synthesis context so LLM names relationships accurately.
*   **Note (2026-07-30):** `_score_edges` already computed `source_type`/`target_type` and discarded them. The two conflicting edge blocks (`Key Edges` keyed on ids, `_build_edge_tuples` keyed on display labels) are collapsed into one id-keyed fact table carrying both endpoints' type, verdict and score, plus a `high_signal` flag preserving the old `Key Edges` predicate. A missing GTI threat score now renders `unknown` rather than a misleading `0` — presentation only, no score is derived.
*   **Review fixes:** consolidating the two blocks initially made the fact table share the diagram's unfiltered 40-edge cap, which *lost every high-signal edge* on a realistic hunt (measured 0 of 6 surviving past a root with 45 benign adjacent edges — `_score_edges` sorts root-adjacent first and `max(source, target)` hands the root's own score to all its edges, so benign CDN edges outranked confirmed-malicious infrastructure). `_select_diagram_edges` now gives high-signal edges first claim on the budget. Also escaped attacker-controlled display labels (a newline in a `meaningful_name` could inject a whole fabricated fact-table row) and coerced string threat scores to numbers.

### Blocker — none. See "Follow-ups" below for two issues found but deliberately not fixed.

## §8 · Follow-ups identified during Tier 4 (not fixed — need a decision)

1. **`_compute_high_signal` can never flag an entity GTI did not score.** The gate is `score >= 80 or (score > HIGH_SIGNAL_THREAT_SCORE and qualifiers >= 2)`, and an unknown score coerces to `0`, so no number of qualifiers (malicious-vendor count, important relationships, malware↔infra bridge, specialist discovery) can admit it. Per `extract_gti_summary`'s docstring, descriptor-only pivot entities normally arrive with no `gti_assessment` at all, so the High-Signal Nodes block effectively contains only triage-discovered root-adjacent entities. This appears to contradict S1-T2's stated intent ("relax synthesis gate so high-scoring items **or specialist-discovered items** surface cleanly") — the specialist-discovery qualifier was added but gated behind `score > 60`, which those entities can never reach. It also compounds edge ranking, since `_score_edges` gives `+1 qualifier` for `target in high_signal_node_ids`. Possible shapes: admit on `qualifiers >= 3` when `not score_known`, or treat an unknown score as neutral rather than `0` in the gate. **Not changed here** — it alters the tuned synthesis gate and is outside S4-T5's scope.

    Concrete evidence of the knock-on, measured on a 46-edge graph (malicious file root, 30 benign CDN domains, 8 descriptor-only dropped files, a malicious URL, a C2 domain resolving to 6 malicious IPs): **6 of the 8 specialist-discovered dropped files were evicted from the 40-edge budget while all 31 benign `contacted_domains` edges were kept.** Mechanism: `_score_edges` gives `+10` for a relationship in `IMPORTANT_RELATIONSHIPS` (which includes `contacted_domains` but not the `dropped` rel_type the malware tool writes), and every root-adjacent edge already inherits the root's own score via `max(source, target)`. So a zero-detection CDN domain scores 102 and a dropped malware artifact scores 92. Because a descriptor-only entity has neither a verdict nor a vendor count, it can never be `has_threat_signal`, so the high-signal reservation added in S4-T5 does not rescue it either. Two candidate fixes, both tuning decisions: add `dropped` to `IMPORTANT_RELATIONSHIPS`, and/or stop letting root-adjacency propagate the root's score to edges whose *target* carries no signal of its own.
2. **`backend/requirements.txt` leaves `mcp` and `langgraph` unpinned.** A fresh build today resolves `mcp` to 2.0.0, which removed `mcp.server.fastmcp` — `backend/mcp/gti/server.py:22` and `backend/mcp/shodan/server.py:4` would fail to import and both MCP servers would be dead on arrival. Pinning affects deploys, so left alone.

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
