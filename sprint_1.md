# Sprint 1 — Tiered Accuracy & Optimisation Plan

> **Owner:** project_harimau · **Created:** 2026-05-20 · **Status:** ⏳ Planned
> **Pick-up agent:** Read this file top-to-bottom. Tasks are tiered by impact; complete Tier 1 before Tier 2 before Tier 3 before Tier 4. Within a tier, tasks are independent unless a dependency is called out.
> **Execution model:** This project runs **only on Google Cloud Run**. There is no local execution step. All verification is via deploy → hit deployed endpoint → inspect Cloud SQL state → user-driven browser check for UI. Do not add steps that require `npm run dev`, `uvicorn`, `docker-compose`, or local fixture runs.
> **Ground truth:** All findings in this file were verified against the **current code**, not the docs. Where docs and code drift, the code wins for execution; flag the drift and update `docs/CHANGELOG.md` + `docs/implementation_plan_v2.md`.

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

# TIER 1 — Hunt Accuracy

**Goal:** every multi-pivot hunt produces a measurably more grounded synthesis report. This is the highest-value tier and should ship first.

**Tier complete when:**
- Re-run §7 fixture; synthesis "Key Indicators" includes **≥1 specialist-discovered IOC with non-zero `threat_score`** (baseline: 0).
- `peer_findings_injected` log events fire at iteration ≥2 for both specialists.
- No regression on a clean-verdict IOC (specialists don't loop unnecessarily).

---

### S1-T1 · Cross-agent peer findings into specialist prompts

**Files:** `backend/agents/malware.py` (~line 506), `backend/agents/infrastructure.py` (~line 471), `backend/agents/lead_hunter_planning.py` (113-129, 131-137)

**Verified current state:**
- `lead_hunter_planning.py:113-129` already dumps both specialists' `network_indicators` and `related_indicators` into the **planner's** `context_str`. The planner LLM sees peer output.
- BUT each specialist's own prompt only reads its **own** prior markdown report (malware.py:506, infra.py:471). The specialist never sees the peer's structured findings.
- The "already analysed" guard at `lead_hunter_planning.py:131-137` is **per-agent only**. Cross-agent re-tasking is not blocked.

**Change:**
- In `malware.py` at the prompt section that injects `previous_report`, additionally read `state["specialist_results"]["infrastructure"]` and inject a `## Peer Specialist Findings (Infrastructure)` block: `verdict`, `summary` (first 800 chars), top-10 `related_indicators`, top-10 `pivot_findings`. Symmetric for `infrastructure.py` reading `["malware"]` — inject `network_indicators`, `host_indicators`, `mitre_techniques`.
- Hard-cap injected block at ~2 KB; truncate by item count, not string slicing.
- Skip silently on iteration 0 (no peer result yet).
- Add `logger.info("peer_findings_injected", agent=…, peer=…, count=…)`.
- **Cross-agent dedup:** in the planner, when constructing subtasks, also exclude entities present in the **peer's** `analyzed_targets` list. Extend the existing dedup at lines 131-137 to union both specialists' lists when computing "already analysed".

**Verify (Cloud Run):**
- Deploy via `cloudbuild-backend.yaml`; trigger §7 fixture via `POST /api/investigate`; poll until done.
- `gcloud logging read 'jsonPayload.event="peer_findings_injected"'` returns ≥2 rows for the job.
- Inspect persisted job in Cloud SQL: `specialist_results.infrastructure.pivot_findings` contains ≥1 entry whose ID originated in `malware.analyzed_targets` from iteration 1, and vice versa.

**Risk:** Token budget. If both peers contribute large `summary` text, prefer the structured arrays over prose.

---

### S1-T2 · GTI attribute propagation + synthesis selector relaxation (bundled)

**Files:** `backend/agents/malware.py:396, 422`, `backend/agents/infrastructure.py:327, 357, 387`, `backend/utils/graph_cache.py`, `backend/agents/lead_hunter_synthesis.py:260-280`

**Verified current state:**
- Specialist `add_entity` calls only pass a context tag, no GTI attrs:
  - `malware.py:396` → `cache.add_entity(eid, "file", {"malware_context": "dropped_file"})`
  - `malware.py:422` → `cache.add_entity(eid, h_type, {"malware_context": f"contacted_{h_type}"})`
  - `infrastructure.py:327, 357, 387` → `cache.add_entity(eid, h_type, {"infra_context": f"<domain|ip|url>_{relationship}"})`
- `graph_cache.add_entity` (lines 40-73) already does deep-merge with list-union, so later attribute additions safely merge.
- `lead_hunter_synthesis.py:260-280` high-signal selector requires `score > HIGH_SIGNAL_THREAT_SCORE` **AND** `qualifiers >= 2`. Qualifiers: `malicious_count > 5`, ≥2 important relationships, or bridges malware↔infra. **Specialist-pivoted entities typically have only 1 relationship (from their discoverer) so even with high score they fail the gate.** T2 lands the data; T2's selector edit lets it surface.

**Change (Part A — propagation):**
- Add helper in `graph_cache.py`: `extract_gti_summary(rel_item: dict) -> dict` returning `{gti_assessment, meaningful_name, names, last_analysis_stats, malicious_count}` if present in the relationship envelope. Returns `{}` if envelope is sparse.
- At each of the 5 call sites, merge `extract_gti_summary(rel_item)` into the attributes dict.
- **Do not derive `threat_score`** — read it straight from `gti_assessment.threat_score.value`. `malicious_count` from `last_analysis_stats.malicious` is a copy, not a derivation, which is fine.

**Change (Part B — selector relaxation):**
- In `lead_hunter_synthesis.py:260-280`, change the gate to:
  ```
  if node["score"] >= 80:
      qualifies = True        # high enough score alone is sufficient
  else:
      qualifies = node["score"] > HIGH_SIGNAL_THREAT_SCORE and qualifiers >= 2
  ```
- Additionally count `"discovered_by_specialist"` as a qualifier: if any of `malware_context` / `infra_context` is set on the node, add 1 qualifier. This lets pivots clear the gate as the cross-agent context grows.

**Verify (Cloud Run):**
- After deploy + §7 fixture run, query persisted graph: target ≥70% of non-triage nodes have `gti_assessment.threat_score.value` set (some pivots genuinely have no GTI data).
- Synthesis "Key Indicators" table includes ≥1 specialist-discovered pivot. **This is the Tier 1 completion trigger.**

**Risk:** Relaxing the selector slightly widens the "Key Indicators" table. Compare row counts vs baseline; if >2× growth, tighten the discovered-by-specialist qualifier to require also `malicious_count >= 1`.

---

### S1-T3 · Indicator parser regex + JSON `raw_text` fallback

**Files:** `backend/agents/malware.py:695`, `backend/agents/infrastructure.py:682`, `backend/utils/agent_utils.py` (`parse_llm_json`)

**Verified current state:**
- Both files use `indicator.split(":", 1)` then check `"ip" in token.lower()` / `"domain" in token.lower()`. Labels like `"C2 Domain: example.com"` work, but `"Compromised IP Address: ..."` is fragile.
- On `FINAL_ITERATION_PROMPT` JSON parse failure, the specialist falls back to a zeroed schema. Raw LLM text is logged but not stored in `specialist_results`, so synthesis has nothing.

**Change:**
- Replace split+`in` with regex (case-insensitive, after `.strip()`):
  ```
  ^(?P<type>IP(?:\s*Address)?|Domain|URL|File|Hash|SHA256|MD5)\s*:\s*(?P<value>.+)$
  ```
  Normalise matched `type` to canonical `IP|Domain|URL|File`. Log unmatched lines at WARNING.
- In `parse_llm_json()`, when JSON parsing fails after the final-iteration call, store the raw LLM text under `specialist_results[agent]["raw_text"]`. Synthesis should prefer `raw_text` over the zeroed schema if `summary` is empty.

**Verify:** Unit tests in `backend/tests/test_indicator_parser.py` for `"C2 Domain: example.com"`, `"IP Address: 1.2.3.4"`, `"SHA256: abc..."`, `"File: <hash>"`, malformed `"weird-no-colon"`. Fixture for malformed JSON LLM response: assert `raw_text` populated, synthesis falls back to it. Tests run in Cloud Build pipeline.

**Risk:** None — purely defensive.

---

### S1-T4 · Triage signal threshold inclusive

**Files:** `backend/agents/triage.py:24, :783`

**Verified current state:** `SIGNAL_MALICIOUS_VENDORS = 3 # Include if EXCEEDS this value`, used as `> SIGNAL_MALICIOUS_VENDORS`. Entities at exactly 3 detections are dropped — these are often the highest-value early-warning pivots.

**Change:** Line 783 `>` → `>=`. Update the constant's comment to "Include if malicious vendor count ≥ this value".

**Verify:** Deploy + re-run 3-5 historical fixtures from `download_reports.py`. Log subtask count delta. Expect modest growth, not >2×.

**Risk:** False-positive widening. If delta >2× on historical fixtures, raise floor to 4 instead of reverting.

---

# TIER 2 — State Machine & Graph Cache Optimisation

**Goal:** eliminate silent data loss in the persistence layer. Lower visibility than Tier 1, but reduces future bug surface and is a hard prerequisite for any future graph-query work.

**Tier complete when:**
- `rg "concat_reports|loop_count|lead_plan" backend/ app/` returns 0 hits.
- Two-iteration hunt with parallel specialists: edge count stable across re-runs (no doubling).
- Re-submitting the same IOC with mixed case (`"Example.COM"` vs `"example.com"`) lands on the same persisted job graph node count.

---

### S2-T1 · State cleanup + `tasked_entities` reducer

**Files:** `backend/graph/state.py:13-17, :85, :93, :97`, `backend/main.py:331`, `backend/agents/lead_hunter.py:92, :102`

**Verified current state:**
- `concat_reports` (state.py:13-17): defined, never bound to any field. Dead.
- `loop_count` (state.py:85, `operator.add`): only `main.py:331` initialises to 0. Never incremented or read. Dead with a footgun reducer.
- `lead_plan` (state.py:93): no `Annotated[..., reducer]`. No writes, no reads. Dead.
- `tasked_entities` (state.py:97, `operator.add`): **not dead** — read at `lead_hunter.py:92`, written `:102`. But `operator.add` causes unbounded duplicate growth across iterations.

**Change:**
1. Delete `concat_reports` function from `state.py`.
2. Delete `loop_count` field from `AgentState` and the initialiser in `main.py:331`.
3. Delete `lead_plan` field from `AgentState`.
4. Change `tasked_entities` reducer: write a `union_lists(a, b)` reducer (set-union with stable ordering) and apply it. Or change to `last_value` and accumulate explicitly inside `lead_hunter.py:102` via `list(set(prev_tasked | new_entity_ids))`.

**Verify:** `rg "concat_reports|loop_count|lead_plan" backend/ app/` → 0 hits. Two-iteration parallel hunt completes without state errors. Inspect `tasked_entities` in persisted job: no duplicates.

**Risk:** Low. Three dead, one reducer change.

---

### S2-T2 · MultiDiGraph merge: list-union node attrs + edge dedup

**Files:** `backend/graph/state.py:19-50` (`merge_graphs`), `backend/utils/graph_cache.py:75-91` (`add_relationship`)

**Verified current state:**
- `state.py:40`: same-node attribute merge is `combined.nodes[node].update(data)` — flat dict.update. List-valued attrs (`flags`, `analyzed_by`, etc.) overwritten by b. Different from `graph_cache.add_entity:40-73` which already deep-merges with list-union. The state-level merge is the regression vector.
- `graph_cache.add_relationship:90`: unconditional `self.graph.add_edge(...)` — no dedup. Calling it twice with same `(source, target, rel_type)` creates two edges.

**Change:**
- In `state.py:40`, replace `update(data)` with a `_merge_node_attrs(existing, incoming)` helper mirroring `graph_cache.add_entity`'s deep-merge. Extract the merge logic to a shared util in `backend/utils/graph_cache.py` and import in both places.
- In `graph_cache.add_relationship`, guard: if an edge `(source_id, target_id)` with the same `relationship` value already exists, merge metadata into it instead of adding a parallel edge. Dedup key: `(source, target, rel_type, first_seen)` when `first_seen` is in metadata, else `(source, target, rel_type)`.

**Verify:** Unit tests in `backend/tests/test_graph_merge.py`:
1. Two graphs share a node with `flags=["x"]` and `flags=["y"]`; merged node has `flags=["x","y"]`.
2. Call `add_relationship(A, B, "resolves_to")` twice → edge count = 1.
3. Cloud Run deploy + re-run §7 fixture twice; assert edge count is stable.

**Risk:** Genuinely distinct relationships (two `resolutions` edges with different `first_seen` dates) must not collapse. The dedup key handles this.

---

### S2-T3 · Entity-ID normalisation (cache + root IOC on intake)

**Files:** `backend/utils/graph_cache.py` (`add_entity`, `add_relationship`), `backend/main.py` (intake handler for `POST /api/investigate`)

**Verified current state:**
- `graph_cache.add_entity:50` uses the raw string as node key. No case/whitespace normalisation. Domains arrive case-mixed from GTI; IPs occasionally carry trailing whitespace.
- `state["ioc"]` is set from the API payload as-is. Compared against cache node IDs at `lead_hunter_planning.py:141, :145`, `lead_hunter_synthesis.py:218`, `triage.py:601`. If the cache normalises but `state["ioc"]` does not, root-IOC lookups fail.

**Change:**
- Add helper `_normalise_id(entity_type: str, value: str) -> str` in `graph_cache.py`:
  - `domain` / `email`: `value.strip().lower()` + IDNA decode if possible
  - `ip` / `ip_address`: `ipaddress.ip_address(v.strip()).compressed`
  - `file` / `hash`: `value.strip().lower()`
  - `url`: `value.strip()` (case-preserving — paths are case-sensitive)
- Apply on `add_entity`, `add_relationship`, and on **intake** in `main.py` when assigning `state["ioc"]`. Same helper used in all places.

**Verify:** Unit test: inserting `"Example.com"` and `"example.com"` collapses to one node. Cloud Run: submit the same IOC with mixed case twice; persisted graph has the same node count.

**Risk:** Existing persisted graphs may have duplicate nodes. Migration is out of scope — add `# TODO: data migration` comment.

---

# TIER 3 — Visual Representation (bounded)

**Goal:** the smallest, highest-impact frontend changes that improve hunt comprehension. A full UX rebuild is under consideration; this tier is intentionally narrow so the work isn't wasted if rebuild proceeds.

**Tier scope rule:** only the three changes below. No refactors, no library swaps, no test infra changes.

**Tier complete when:**
- Cloud Build deploys cleanly (type-check + build passes).
- User verifies legend, gradient, and focus mode in the deployed Cloud Run frontend URL.

---

### S3-T1 · Graph legend

**File:** `app/src/app/investigate/[id]/page.tsx`

**Change:** Add a collapsible panel pinned bottom-left of the graph panel. Three lines:
- "● Root IOC · cyan"
- "● Malicious · pink border"
- "● Type colours: file=purple · domain=orange · IP=teal · URL=blue"

Use existing colour constants. Closed by default; remembers state in `localStorage`.

**Verify:** Type-check + Cloud Build deploy succeed. User confirms legend appears in deployed frontend.

---

### S3-T2 · Threat-score gradient on `CustomNode`

**File:** `app/src/app/investigate/[id]/page.tsx` (CustomNode ~lines 183-237)

**Dependency:** S1-T2 must be deployed first so specialist-discovered nodes carry `threat_score`.

**Change:** Replace the binary malicious border with a fill gradient: `threat_score < 40 → green tint`, `40-70 → amber`, `≥70 → red`. Keep the malicious border as an additional cue. Read `threat_score` from `gti_assessment.threat_score.value` on the node payload (already flattened by `format_graph_from_cache`).

**Verify:** Cloud Build deploy succeeds. User confirms ≥3 nodes show distinct gradient colours in the deployed frontend.

**Risk:** None — purely visual.

---

### S3-T3 · Focus mode (2-hop dim)

**File:** `app/src/app/investigate/[id]/page.tsx`

**Change:** Add a "Focus" toggle to the existing filter row. When ON, clicking a node dims (`opacity: 0.15`) all nodes >2 hops away (BFS on the edge list). Background click or toggle-off resets opacities. State scoped to the page; not persisted.

**Verify:** Cloud Build deploy succeeds. User confirms focus mode dims correctly and resets cleanly.

**Risk:** Position jumpiness on filter toggle is a known issue and explicitly out of scope here.

---

# TIER 4 — Remaining Optimisations

**Goal:** lower-priority structural improvements. Pick up after Tier 1-3 ship and have soaked for at least one user-driven hunt cycle.

**Tier complete when:** each task below has its own Verify line met. No tier-wide gate — Tier 4 may slip to a follow-up sprint without blocking the Sprint 1 review.

---

### S4-T1 · Strict structured output

**Files:** all of `backend/agents/*.py`

**Change:** Migrate specialist JSON outputs from `parse_llm_json()` to LangChain `with_structured_output()` with Pydantic schemas. Closes the open Pillar 4 · Milestone 4 task. Keep `raw_text` fallback from S1-T3 as a safety net.

**Verify:** All specialists produce schema-valid outputs across 5 historical fixtures.

---

### S4-T2 · Native LangGraph `ToolNode` for specialists

**Files:** `backend/agents/malware.py`, `backend/agents/infrastructure.py`

**Change:** Replace the internal Python `while/for` tool loops with LangGraph's native `ToolNode` + conditional edges. Improves checkpoint visibility and removes the manual orchestration in each specialist. Closes the open Pillar 4 · Milestone 4 task.

**Verify:** Tool-call traces visible in LangGraph checkpoint history.

---

### S4-T3 · Checkpointer audit

**Files:** `backend/main.py`, `backend/graph/workflow.py`

**Verified current state:** `workflow.py:19` defaults `checkpointer=None`. Docs claim `AsyncPostgresSaver` is wired. Need to confirm `main.py` injects it at runtime.

**Change:** Read `main.py`, locate the LangGraph compile site, confirm the checkpointer is constructed and passed. If missing, wire `AsyncPostgresSaver` with the existing `DATABASE_URL`. Update `docs/CHANGELOG.md` either way to reflect actual state.

**Verify:** Trigger an investigation, force a Cloud Run instance restart mid-hunt, confirm the job resumes from its checkpoint.

---

### S4-T4 · SSE error wrapping + dynamic progress

**File:** `backend/graph/sse_wrappers.py`

**Change:**
- Wrap `emit_event` calls in try/except so a transient SSE broadcast error doesn't abort the node.
- Replace the static progress curve with one driven by `len(state["subtasks"])` × current `iteration`, so a 1-iteration hunt and a 3-iteration hunt show distinct progress shapes.

**Verify:** Force an SSE manager exception; agent node still completes. Compare progress curves between 1-iteration and 3-iteration hunts.

---

### S4-T5 · Synthesis quality

**File:** `backend/agents/lead_hunter_synthesis.py`

**Change:**
- Edge tuples passed to the synthesis LLM include attributes (`source_type`, `target_verdict`, `rel_type`) so the LLM names relationships rather than infers them.
- Deduplicate specialist `summary` text from the synthesis prompt (currently included twice — once in specialist context, once inline).

**Verify:** Synthesis report references edge labels by their actual `rel_type`, not paraphrased.

---

## §6 · Critical files reference (verified line numbers)

```
backend/agents/triage.py                      24 (const), 783 (filter)
backend/agents/malware.py                     396, 422 (add_entity), 506 (prompt prev_report), 695 (split parser)
backend/agents/infrastructure.py              327, 357, 387 (add_entity), 471 (prompt prev_report), 682 (split parser)
backend/agents/lead_hunter.py                 92, 102 (tasked_entities r/w) — active orchestrator
backend/agents/lead_hunter_planning.py        113-129 (context dump), 131-137 (per-agent dedup), 141-145 (root_ioc compare), 187 (json.loads)
backend/agents/lead_hunter_synthesis.py       218 (root_ioc), 260-280 (high-signal selector)
backend/graph/workflow.py                     do NOT edit line 127 (intentional `>`)
backend/graph/state.py                        13-17 (concat_reports — delete), 40 (merge_graphs — fix), 85, 93 (dead fields — delete), 97 (tasked_entities reducer — fix)
backend/utils/graph_cache.py                  40-73 (add_entity — extract deep-merge helper), 75-91 (add_relationship — add dedup)
backend/utils/agent_utils.py                  parse_llm_json (raw_text fallback)
backend/main.py                               331 (drop loop_count init), intake handler (normalise state["ioc"])
app/src/app/investigate/[id]/page.tsx         CustomNode (~183-237), filter row
docs/implementation_plan_v2.md                Pillar 3 M2, Pillar 4 M4, Pillar 5 M3, Pillar 6 M3 — tick as you go
docs/CHANGELOG.md                             one dated entry per tier
```

---

## §7 · Canonical test fixture

For every Verify step, hunt the same two IOCs against the deployed Cloud Run backend:

1. **A multi-pivot file hash** — start with `44d88612fea8a8f36de82e1278abb02f` (PRD example).
2. **A C2 domain** flagged malicious in GTI with ≥5 communicating files.

Per-task metrics captured (compared against `sprint_baselines/sprint_1_baseline.md`):
- `final_report` markdown length & "Key Indicators" row count
- Persisted-graph nodes with non-null `threat_score`
- Edge count (must not double after S2-T2)
- Hunt total wall-clock (must not regress >20%)

---

## §8 · Handoff notes

- **Memory:** `feedback_agent_prompts` (don't derive `threat_score`, don't touch Shodan prompt section) and `feedback_working_style` (propose before implementing; commit messages short one-liners).
- **Order:** Tier 1 → Tier 2 → Tier 3 → Tier 4. Within Tier 1: T1 + T2 first (largest accuracy gain, independent), then T3/T4 in parallel. Tier 3 T2 depends on Tier 1 T2 being deployed.
- **Per FRAMEWORK.md:** tick `docs/implementation_plan_v2.md` as you go (`[/]` → `[x]` with date). Append Challenges & Learnings notes for non-obvious findings.
- **Commit hygiene:** one commit per task ID, subject `feat(s1-<tier>-T<N>): …`. One rollup PR per tier.
- **No local runs.** All verification is Cloud Run deploy → endpoint hit → Cloud SQL inspection → user-driven browser check.
- **If blocked:** add `### Blocker — <task>` at bottom of this file and stop — do not silently proceed past the blocker.

---

## §9 · Sprint review checklist

- [ ] Tier 1 complete (specialist pivot in Key Indicators table, peer findings injected at iter ≥2)
- [ ] Tier 2 complete (dead fields gone, edges stable, mixed-case IOCs collapse)
- [ ] Tier 3 complete (legend / gradient / focus user-verified in Cloud Run frontend)
- [ ] Tier 4 items captured (may slip to a follow-up sprint — that's fine if Tier 1-3 shipped)
- [ ] `docs/implementation_plan_v2.md` ticked with dates
- [ ] `docs/CHANGELOG.md` updated — one dated entry per tier
- [ ] `git log --oneline` shows the expected commit-per-task structure
- [ ] No regression on clean-verdict IOC (specialists don't loop unnecessarily)

---

_End of Sprint 1 plan. Subsequent sprints will be authored as `sprint_2.md` if Tier 4 slips, or as net-new work after Tier 3 ships._
