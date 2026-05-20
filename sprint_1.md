# Sprint 1 — Hunt Accuracy: Cross-Agent Context & Graph Fidelity

> **Owner:** project_harimau · **Created:** 2026-05-20 · **Status:** ⏳ Planned
> **Pick-up agent guidance:** Read this entire file first, then `docs/FRAMEWORK.md`, then the "Critical files" list in §6 below. Every task has a file path, expected change, and verification step. Do not skip §1 (alignment) or §7 (handoff).
> **Ground truth:** All findings in §3 were verified against the **current code**, not the docs. Where the docs and code drift (e.g., the `iteration > max_iterations` change, the `AsyncPostgresSaver` claim), the code wins. If you find code that contradicts a task here, stop and update this file before proceeding.

---

## 1. Sprint Alignment

This sprint slots into **`docs/implementation_plan_v2.md`** as follows:

| Sprint task cluster | Maps to existing milestone | Notes |
|---|---|---|
| Cross-agent context propagation | Pillar 3 · Milestone 2 (Specialist Suite) | New tasks — append, don't rewrite |
| Specialist-discovered entity GTI propagation | Pillar 4 · Milestone 4 (Flow & Robustness) | Adds to the open `[ ]` list |
| Strict JSON output via `with_structured_output()` | Pillar 4 · Milestone 4 task already open | Mark `[/]` when started |
| State-machine cleanup (`concat_reports`, `loop_count`, `lead_plan`) | Pillar 2 · Milestone 1 | Bug-fix tasks |
| MultiDiGraph merge edge dedup + list-union | Pillar 4 · Milestone 4 task already open | Mark `[/]` when started |
| Entity-ID normalisation (case/whitespace) | Pillar 5 · Milestone 3 (Graph Persistence) | New task |
| Frontend legend + threat gradient + focus mode | Pillar 6 · Milestone 3 | Append to open list; tag `🧪` if rebuild deferred |

**Update `implementation_plan_v2.md` as you go**: per `docs/FRAMEWORK.md`, mark `[/]` when starting, `[x]` when done, include a timestamp on significant items, and never delete superseded tasks.

**Frontend caveat:** The user is considering a full UX rebuild. **Do not refactor the existing frontend deeply.** Only ship the three smallest, highest-impact UX wins in §5 (legend, threat gradient, focus mode). Larger UX changes are deferred to a possible Sprint N rebuild.

---

## 2. Sprint Goal

Make every multi-pivot hunt produce a measurably more grounded final report by:

1. **Specialists see each other's findings** across iterations (the biggest single accuracy gap).
2. **Specialist-discovered entities carry GTI attributes** so synthesis can reason about them.
3. **No more silent data loss** in JSON parsing, signal filtering, or graph merging.
4. **The frontend exposes threat density and focus** so an analyst can read the hunt in <60 seconds.

### Definition of done for the sprint

- A re-run of the canonical test IOC (see §8) produces a synthesis report that **mentions at least one specialist-discovered pivot in the `## Key Indicators` table with non-zero `threat_score`**. Today it does not.
- `specialist_results.malware.peer_findings` and `.infrastructure.peer_findings` are populated by iteration ≥2.
- All Sprint 1 tasks ticked in `implementation_plan_v2.md` with timestamps.
- No regression on a clean-verdict IOC (false-positive hunt depth).

---

## 3. Sprint 1 backlog (this sprint, in order)

Each task uses this contract for the pick-up agent:

```
ID  | Title
File(s) | exact path(s)
Change  | what to do, briefly
Verify  | how to confirm it works
Risk    | what to watch out for
```

---

### S1-T1 · Wire peer findings into specialist prompts

**File(s):** `backend/agents/malware.py` (~line 506), `backend/agents/infrastructure.py` (~line 471), `backend/agents/lead_hunter_planning.py` (113-129)

**Current state (verified in code, not docs):**
- `lead_hunter_planning.py:113-129` *already* dumps `network_indicators` and `related_indicators` from both specialists into the **planner's** `context_str`. So the planner LLM sees peer output when generating the next round of subtasks.
- BUT each specialist's own prompt only reads its **own** prior markdown report:
  - `malware.py:506` → `state["specialist_results"]["malware"]["markdown_report"]`
  - `infrastructure.py:471` → `state["specialist_results"]["infrastructure"]["markdown_report"]`
- The specialist never sees the peer's structured `network_indicators` / `related_indicators` / `summary`. So malware in iteration 2 may be tasked with "analyze IP 1.2.3.4" but won't know infra found it had open RDP and a malicious JARM.

**Change:**
- In `malware.py` ~line 506 (the system prompt section that injects `previous_report`), additionally read `state["specialist_results"]["infrastructure"]` and inject a `## Peer Specialist Findings (Infrastructure)` block containing: `verdict`, `summary` (first 800 chars), top-10 `related_indicators`, top-10 `pivot_findings`. Symmetric edit in `infrastructure.py` ~line 471 reading from `["malware"]` and injecting `network_indicators` / `host_indicators` / `mitre_techniques`.
- Only include if the peer result exists (iteration ≥ 2). Skip silently on first iteration.
- Add `logger.info("peer_findings_injected", agent=…, peer=…, count=…)`.

**Verify:**
- Grep structured logs for `peer_findings_injected` events at iteration ≥ 2.
- Re-run §8 fixture; assert infra's `pivot_findings` or `related_indicators` include at least one indicator that originated from malware iteration 1 (and vice versa).

**Risk:** Token budget. Hard-cap the injected block at ~2 KB; truncate by item count (not string slicing). If both peers contribute a large `summary`, prefer the structured arrays over prose.

---

### S1-T2 · Propagate GTI attributes onto specialist-discovered entities

**File(s):** `backend/agents/malware.py` (lines 396, 422), `backend/agents/infrastructure.py` (lines 327, 357, 387), `backend/utils/graph_cache.py`

**Current state (verified):**
- Confirmed call sites: each writes only a context tag, e.g.
  - `malware.py:396` → `cache.add_entity(eid, "file", {"malware_context": "dropped_file"})`
  - `malware.py:422` → `cache.add_entity(eid, h_type, {"malware_context": f"contacted_{h_type}"})`
  - `infrastructure.py:327, 357, 387` → `cache.add_entity(eid, h_type, {"infra_context": f"<domain|ip|url>_{relationship}"})`
- Note: `graph_cache.add_entity` (lines 40-73) already does deep-merge with list-union on existing entities — so propagating GTI attrs *later* will safely merge, it won't overwrite. The fix is purely about including them in the **initial** call.

**Change:**
- For each call site, inspect the source `rel_item` / tool response and, if it contains an `attributes` block (it usually does for GTI relationship payloads — `communicating_files`, `resolutions`, etc.), copy the small set of fields the synthesis selector reads: `gti_assessment`, `meaningful_name`, `names`, `last_analysis_stats`, plus a derived `malicious_count` from `last_analysis_stats.malicious`.
- Add helper in `graph_cache.py`: `extract_gti_summary(rel_item: dict) -> dict` that returns this small projection (returns `{}` if not available). Use at all 5 call sites.
- **Fallback path (optional, gated):** if envelope lacks attributes AND entity appears in ≥2 relationship sets, fire a single `get_<type>_report` MCP call. Hard cap: 5 such fetches per investigation. Tag the resulting node with `enriched_via="fallback_fetch"` for telemetry.

**Verify:**
- After a hunt, programmatically count: % of non-triage nodes that have `gti_assessment.threat_score.value` set. Target ≥ 70% (some pivots genuinely have no GTI data).
- Confirm `lead_hunter_synthesis.py:263` high-signal selector now includes ≥1 specialist-discovered pivot in the canonical fixture (§8).

**Risk:** Per memory `feedback_agent_prompts`: never derive `threat_score`. Read `gti_assessment.threat_score.value` straight from the relationship envelope; don't compute. `malicious_count` from `last_analysis_stats.malicious` is fine (that's just a copy, not a derivation).

---

### S1-T3 · Fix indicator-parser drops + JSON fallback dataloss

**File(s):** `backend/agents/malware.py:695` (`parts = indicator.split(":", 1)`), `backend/agents/infrastructure.py:682` (same), `backend/utils/agent_utils.py` (parse_llm_json)

**Current state (verified):**
- Both files use `indicator.split(":", 1)`. The `maxsplit=1` means colons inside values aren't an issue, but the LHS type-token must match `"ip"` / `"domain"` substrings. A label like `"C2 Domain"` works for `"domain"` check but `"Compromised IP Address"` doesn't match `"ip"` cleanly via simple `.lower() in` checks — review the exact branch logic in each file before patching.

**Change:**
- Replace the split+`in` heuristic with regex over known prefixes:
  `^(?P<type>IP(?:\s*Address)?|Domain|URL|File|Hash|SHA256|MD5)\s*:\s*(?P<value>.+)$` (case-insensitive, applied after `.strip()`).
- Normalise the matched `type` to the canonical set: `IP|Domain|URL|File`.
- Log unmatched lines at WARNING with the raw indicator string so we can tune.
- In `parse_llm_json()`, when JSON parsing fails on a `FINAL_ITERATION_PROMPT` call, store the raw LLM text under `specialist_results[agent]["raw_text"]` instead of returning the zeroed schema silently. Synthesis should prefer `raw_text` if `summary` is empty.

**Verify:** Add unit tests for: `"C2 Domain: example.com"`, `"IP Address: 1.2.3.4"`, `"SHA256: abc..."`, `"File: <hash>"`, malformed `"weird-no-colon"`. Add a fixture for a malformed JSON LLM response and assert `raw_text` is populated and synthesis falls back to it.

**Risk:** None — purely defensive. Existing well-formed outputs still match the regex.

---

### S1-T4 · Triage signal threshold: inclusive

**File(s):** `backend/agents/triage.py:24`, `:783`

**Current state (verified):**
- `triage.py:24`: `SIGNAL_MALICIOUS_VENDORS = 3   # Include if malicious vendor count EXCEEDS this value`
- `triage.py:783`: `or (e.get("malicious_count") or 0) > SIGNAL_MALICIOUS_VENDORS`
- The constant's own comment explicitly says EXCEEDS — so 3 is intentionally exclusive. But early-campaign IOCs at exactly 3 detections are the highest-value early-warning pivots and they're currently dropped.

**Change:**
- Option A (preferred): change `>` to `>=` on line 783. Update the constant's comment to "Include if malicious vendor count ≥ this value". Leave the constant value at 3.
- Option B: lower the constant to 2 and keep `>`. Equivalent floor of 3. Less clear, don't do this.

**Verify:** Hunt an IOC with a relationship entity at exactly 3 detections; confirm it now reaches the LLM context and downstream specialists. Run 3-5 historical fixtures before/after and log the subtask count delta — should grow modestly, not explode.

**Risk:** False-positive widening if many low-conviction 3-vendor hits sneak through. If the count delta is >2× on historical fixtures, raise the floor to 4 rather than reverting.

---

### S1-T5 · State machine cleanup

**File(s):** `backend/graph/state.py:13`, `:85`, `:93`; `backend/main.py:331`

**Current state (verified by grep):**
- `concat_reports` (state.py:13-17): defined, never bound to any field. Dead code.
- `loop_count` (state.py:85, reducer `operator.add`): only reference outside state.py is `main.py:331` initialising it to `0`. Nothing increments it. Nothing reads it. Dead field with a footgun reducer.
- `lead_plan` (state.py:93): `Optional[str]` *without* `Annotated[..., reducer]`. No writes, no reads anywhere. Dead.

**Change:**
1. **`concat_reports`**: delete the function definition. There's no consumer.
2. **`loop_count`**: delete the field from `AgentState` and the initialiser line in `main.py:331`. Confirm `rg loop_count backend/` returns no hits after.
3. **`lead_plan`**: delete the field from `AgentState`.
4. **`workflow.py:127` (`iteration > max_iterations`)**: leave alone. Architecture changelog confirms `>` is intentional to allow synthesis at the final iteration.

**Verify:** `rg "concat_reports|loop_count|lead_plan" backend/ app/` returns 0 hits after the patch. Run a 2-iteration hunt with both specialists in parallel — should complete without state-related errors.

**Risk:** Low. All three are confirmed unused.

---

### S1-T6 · MultiDiGraph merge: edge keys + list-union attributes

**File(s):** `backend/graph/state.py:19-50` (`merge_graphs`), `backend/utils/graph_cache.py:75-91` (`add_relationship`)

**Current state (verified):**
- `state.py:40`: when both `a` and `b` contain the same node, `combined.nodes[node].update(data)` — flat dict.update. List-valued attrs (`flags`, `analyzed_by`, etc.) get overwritten by b. Note: this is DIFFERENT from `graph_cache.add_entity` (lines 40-73) which already does deep-merge with list-union. The state-level merge is the regression vector.
- `state.py:46-47`: every edge from b is added with `combined.add_edge(u, v, key=key, **data)`. `MultiDiGraph.add_edge` with the same key replaces, but if specialists call `add_relationship` repeatedly during one iteration (cache-level), then `merge_graphs` runs across parallel branches, edges can fan out.
- `graph_cache.add_relationship:90`: unconditional `self.graph.add_edge(...)` — no dedup. Calling it twice with the same `(source, target, rel_type)` creates two edges with auto-keys.

**Change:**
- In `state.py:40`, replace `combined.nodes[node].update(data)` with a helper `_merge_node_attrs(existing, incoming)` mirroring the cache's deep-merge semantics (list-union, dict-recurse, b-wins on scalar conflict). Re-use the logic from `graph_cache.add_entity` (or extract it to a shared util).
- In `graph_cache.add_relationship`, add a guard: if an edge `(source_id, target_id)` with the same `relationship` value already exists, merge metadata into it instead of adding a parallel edge. Use the existing edge-iteration pattern from `get_neighbors:146`.
- Addresses open Pillar 4 · Milestone 4 task: *"Optimize NetworkX MultiDiGraph Merges"*.

**Verify:** Unit test:
1. Construct two graphs `a` and `b` that share a node with `flags=["x"]` and `flags=["y"]` respectively; assert merged node has `flags=["x","y"]`.
2. Call `add_relationship(A, B, "resolves_to")` twice; assert edge count is 1, not 2.
3. Re-run §8 fixture; record edge count, then re-run same fixture and assert edge count is stable across runs.

**Risk:** If two genuinely distinct relationships exist (e.g., two `resolutions` edges with different `first_seen` dates), do not collapse them. Use `(source, target, rel_type, first_seen)` as the dedup key when `first_seen` is in metadata; otherwise `(source, target, rel_type)`.

---

### S1-T7 · Entity-ID normalisation at the cache boundary

**File(s):** `backend/utils/graph_cache.py` (`add_entity`, `add_relationship`)

**Change:**
- Introduce `_normalise_id(entity_type: str, value: str) -> str`:
  - domain/email: `value.strip().lower()` + IDNA decode if possible
  - ip / ip_address: `value.strip()` (do not lowercase IPv6 here without care; use `ipaddress.ip_address(v).compressed`)
  - file/hash: `value.strip().lower()`
  - url: `value.strip()` (don't lowercase — paths are case-sensitive)
- Apply at both insertion and lookup. Update `format_graph_from_cache` if it reconstructs IDs anywhere.

**Verify:** Insert `"Example.com"` and `"example.com"` — should collapse to one node. Add a unit test.

**Risk:** Existing persisted graphs may have duplicates. One-time cleanup migration is out of scope; add a `# TODO: migration` comment.

---

### S1-T8 · Frontend: legend + threat-score gradient + focus mode

**File(s):** `app/src/app/investigate/[id]/page.tsx` only.

> **Bounded scope — full UX rebuild is being considered separately. Do not refactor anything else in this file in this sprint.**

**Change:**
1. **Legend (smallest win, do first):** A collapsible panel pinned bottom-left of the graph. Three lines: "● Root IOC · cyan", "● Malicious · pink border", "● Type colours: file=purple, domain=orange, IP=teal, URL=blue". Use existing colour constants — don't redefine.
2. **Threat-score gradient:** Replace the binary malicious border with a fill gradient on `CustomNode`: <40 green, 40–70 amber, ≥70 red. Keep the malicious border as an additional visual cue. Read `threat_score` from the node payload (now populated by S1-T2).
3. **Focus mode:** Add a "Focus" toggle in the existing filter row. When ON, clicking a node dims (`opacity: 0.15`) all nodes >2 hops away. BFS on the edge list. Reset on toggle-off or background click.

**Verify:**
- Manually drive the frontend with the §8 fixture using the `verify` skill or by running `npm run dev` and screen-checking each of: legend visible, gradient applied to ≥3 nodes, focus mode dims correctly.
- Do not ship if any of the three breaks for any node type.

**Risk:** Position jumpiness on filter toggle (already a known issue) is out of scope. Don't try to fix it here.

---

## 4. Out of scope (deferred to later sprints)

| Item | Why deferred | Next sprint candidate |
|---|---|---|
| Native LangGraph `ToolNode` refactor in specialists | Big change, needs design pass | Sprint 2 |
| `with_structured_output()` to replace `parse_llm_json()` | Touches every agent prompt | Sprint 2 |
| Postgres checkpointer audit (PRD claims done, verify) | Need to inspect `main.py` runtime injection | Sprint 2 |
| Frontend rebuild (full UX redesign) | User is still deciding | Sprint N (pending decision) |
| Hunt comparison / STIX export | UX features, blocked by rebuild decision | Sprint N+1 |
| FalkorDB / cross-investigation graph | Phase 7 — Architecture roadmap item | Pillar 5 future milestone |

---

## 5. Suggested future sprints (roadmap, not commitments)

**Sprint 2 — Structured output + control-flow cleanup**
- Migrate all specialist outputs to LangChain `with_structured_output()` (closes Pillar 4 · Milestone 4 open task).
- Refactor specialist inner loops to native `ToolNode` + conditional edges (open task).
- Remove duplicate post-LLM graph expansion in specialists (open task).
- Audit `main.py` for `AsyncPostgresSaver` injection; reconcile docs vs code.

**Sprint 3 — Synthesis quality**
- High-signal selector: relax to `score >= 80 OR (score > 60 AND qualifiers >= 2)`.
- Edge tuples in synthesis prompt: include edge attributes (`source_type`, `target_verdict`, `rel_type`) so the LLM can name relationships, not infer.
- De-duplicate specialist `summary` text from the synthesis prompt (currently included twice).

**Sprint 4 — Observability**
- Wrap `sse_wrappers.py` emit_event calls in try/except.
- SSE progress driven by `len(subtasks)` × `iteration`, not the static curve.
- Log structured `peer_findings_used` / `peer_findings_dropped` counts for tuning.

**Sprint N — Frontend rebuild (if greenlit)**
- Treat current frontend as legacy; new UX design doc + Figma first.
- Until then, do *only* the three §3 S1-T8 patches.

---

## 6. Critical files for the pick-up agent (verified line numbers)

```
backend/agents/triage.py                      24 (const), 783 (filter)
backend/agents/malware.py                     396, 422 (add_entity), 506 (prompt prev_report), 695 (split parser)
backend/agents/infrastructure.py              327, 357, 387 (add_entity), 471 (prompt prev_report), 682 (split parser)
backend/agents/lead_hunter_planning.py        113-129 (context dump), 187 (json.loads), 191-193 (except returns empty)
backend/agents/lead_hunter_synthesis.py       263 (high-signal selector — read but DO NOT change scope this sprint)
backend/agents/lead_hunter.py                 read in full — confirm orchestrator role vs planning/synthesis split
backend/graph/workflow.py                     do NOT edit line 127 (intentional `>`)
backend/graph/state.py                        13-17 (concat_reports — delete), 40 (merge_graphs node merge — fix), 85, 93 (dead fields — delete)
backend/graph/sse_wrappers.py                 read only this sprint
backend/utils/graph_cache.py                  40-73 (add_entity — extract deep-merge helper), 75-91 (add_relationship — add dedup)
backend/utils/graph_formatter.py              read only
backend/utils/agent_utils.py                  parse_llm_json (raw_text fallback)
backend/main.py                               331 (drop loop_count initialiser)
app/src/app/investigate/[id]/page.tsx         CustomNode (~184-237), filter row
docs/implementation_plan_v2.md                Pillar 3 M2, Pillar 4 M4, Pillar 5 M3, Pillar 6 M3 — tick as you go
docs/agent_implementation.md                  Specialist Handoff section — document T1 contract
```

---

## 7. Handoff notes for the next agent

- **Memory:** Read the user's memory under `.claude/projects/.../memory/` — especially `feedback_agent_prompts.md` (don't derive `threat_score`, don't touch the Shodan section in prompts) and `feedback_working_style.md` (propose before implementing; commit messages short one-liners).
- **Order:** Do S1-T1 → S1-T2 first. They unlock the largest accuracy gain and are independent. S1-T3 through S1-T7 are small, parallelisable. S1-T8 last (only after S1-T2 lands so `threat_score` actually populates).
- **Per FRAMEWORK.md:** Tick `implementation_plan_v2.md` as you go (`[/]` → `[x]` with timestamp). Add Challenges & Learnings notes for anything non-obvious.
- **Commit hygiene:** One commit per task ID. Subject `feat(sprint1-T<N>): <one-liner>`. Match recent style (see `git log --oneline -10`).
- **Verification skill:** Use the `verify` skill or `npm run dev` + manual click-through for S1-T8. Don't claim done on UI changes without seeing the browser render.
- **If blocked:** Add a `### Blocker — <task>` subsection at the bottom of this file describing the blocker and *do not silently proceed past it*.

---

## 8. Canonical test fixture

For every Verify step in this sprint, hunt the same two IOCs:

1. **A multi-pivot file hash** (suggest using one already in `download_reports.py` history if available, otherwise `44d88612fea8a8f36de82e1278abb02f` — the EICAR/PRD example).
2. **A C2 domain** that GTI flags as malicious with ≥5 communicating files.

Before/after each task, capture:
- `final_report` markdown length & "Key Indicators" row count
- Number of nodes in the persisted `investigation_graph` with non-null `threat_score`
- Number of edges (should not double after S1-T6)
- Hunt total wall-clock (should not regress >20%)

---

## 9. Sprint review checklist (run before declaring sprint done)

- [ ] All §3 tasks ticked here and in `implementation_plan_v2.md` with timestamps
- [ ] §8 fixture re-run; "Key Indicators" includes ≥1 specialist-discovered IOC
- [ ] No regression on a clean IOC (specialists don't loop unnecessarily)
- [ ] `git log --oneline` shows one commit per task with the agreed message format
- [ ] `docs/CHANGELOG.md` updated with a single dated entry summarising Sprint 1
- [ ] Memory updated only if something surprising/non-obvious was learned (per memory rules)

---

_End of sprint 1 plan. Subsequent sprints will be authored as `sprint_2.md`, `sprint_3.md`, etc._
