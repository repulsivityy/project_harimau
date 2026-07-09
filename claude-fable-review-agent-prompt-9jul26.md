# Agent Task: Integrate Accuracy Fixes #2, #3, #6 into Project Harimau

## Context

You are working in the `project_harimau` repository. A prior review identified
three accuracy bugs and produced fixes for them, already written and unit-tested
(53/53 passing) in isolation, but **not yet integrated into this repo**.

**Read `claude-fable-review-9jul26.md` in full before making any changes.** It
contains:
- The three problem statements (Section 1)
- The design rationale for non-obvious decisions (Section 3) — read this
  carefully, it explains *why* certain things are built the way they are, and
  two of those decisions came directly from bugs caught during testing
  (specifically 3.1 and 3.2 — do not "simplify" the verdict engine's benign
  handling or the two-pass cascade prevention, they are load-bearing)
- The exact integration points, file by file (Section 4)
- The full source of all four new files (Section 5)

Do not proceed until you've read that file. This prompt tells you what to do;
the review file tells you why.

---

## Your task, in order

### Step 1 — Create the new files

Create these four files with the exact content given in Section 5 of the
review markdown. Do not modify the logic while transcribing — copy verbatim.

- `backend/utils/report_validator.py`
- `backend/utils/signal_filter.py`
- `backend/utils/verdict_engine.py`
- `backend/tests/test_accuracy_fixes.py`

Before writing, check whether `backend/utils/graph_cache.py` currently exposes
`_normalise_id`, `normalize_verdict`, `InvestigationCache.get_entity_full()`,
`.add_entity()`, `.add_relationship()`, and `.graph.nodes()/.successors()/
.predecessors()` with the signatures the new modules expect. If anything has
drifted since this review was written, adapt the new modules' calls to match
the real signatures — do not change `graph_cache.py` itself for this task.

### Step 2 — Run the standalone test suite

```bash
pip install networkx --break-system-packages   # only if missing
python -m pytest backend/tests/test_accuracy_fixes.py -v
```

All 53 tests must pass before you continue. If something fails, it's almost
certainly a shape mismatch between the real `InvestigationCache` and what the
tests assume — fix the adapter code in the new modules, not the test
expectations, unless you can articulate why a specific test's expectation was
wrong given the real repo's data shapes.

### Step 3 — Integrate into `backend/agents/triage.py` (#3)

Per Section 4 / 3.5 / 3.6 of the review:

1. Add `from backend.utils.signal_filter import get_signal_reason, promote_by_graph_context`
2. Remove the now-redundant `SIGNAL_MALICIOUS_VENDORS` module constant (logic
   moved into `signal_filter.py`) — confirm nothing else in the file still
   references it before deleting.
3. In the entity parse loop, before entities are appended to `parsed_entities`,
   attach the full GTI attributes under a private key so the filter can see
   them: `parsed["_full_attrs"] = full_attrs`.
4. Replace the signal-filter block (search for `if rel_name not in
   UNFILTERED_RELATIONSHIPS:`) with a version that calls `get_signal_reason()`
   per entity, keeps survivors, and routes non-survivors into an accumulator
   dict for the promotion pass. Attach `signal_reason` onto surviving entities.
   Strip `_full_attrs` from every entity before it's considered "parsed" —
   it must never reach LLM context or get persisted to the graph as a raw
   attribute blob.
5. Initialize two accumulators near where `relationships_data = {}` is
   declared: a dict of dropped entities and a set of flagged (surviving)
   entity IDs.
6. After the full relationship-parsing loop closes (all `rel_name` iterations
   done, cache fully populated for this investigation), call
   `promote_by_graph_context(cache, dropped_dict, flagged_set)` and fold any
   promoted entities back into `relationships_data` (e.g. under a
   `"graph_context_promoted"` synthetic key) with their `signal_reason` set
   from the promotion reason.
7. Add the "Signal Reasons" paragraph to `TRIAGE_ANALYSIS_PROMPT` as given in
   the review, so the triage LLM doesn't treat low-detection-count entities as
   automatically benign.

Confirm: does `triage.py` reference `SIGNAL_MALICIOUS_VENDORS` anywhere you
didn't touch? If so, either update that reference to use the new module or
leave a `# TODO` and flag it in your summary at the end — don't silently leave
dead code paths.

### Step 4 — Integrate into `backend/agents/lead_hunter.py` (#6, #2)

Per Section 4 of the review:

1. Add imports for `apply_composite_verdicts` from `verdict_engine` and
   `validate_and_annotate` from `report_validator`.
2. In the synthesis branch of `lead_hunter_node` (the code path reached when
   `current_iteration >= MAX_ITERATIONS` or an early-exit condition fires —
   there are three early-exit layers before this point, don't disturb them),
   insert `apply_composite_verdicts(cache, job_id=state.get("job_id"))`
   **before** the call to `generate_final_report_llm`.
3. Wrap the report returned by `generate_final_report_llm` with
   `validate_and_annotate(report_md=..., cache=cache,
   specialist_results=state.get("specialist_results", {}),
   root_ioc=state.get("ioc"), job_id=state.get("job_id"))`.
4. Update the final `return` statement of the synthesis branch to include
   `"investigation_graph": cache.get_state()`. Currently this key is
   deliberately omitted with a comment about avoiding `merge_graphs` — that
   comment is now stale because this step *does* mutate the graph
   (composite verdicts written onto nodes) and it must be persisted or the
   escalations vanish. Confirm there's no parallel writer at this exact point
   in the graph (there shouldn't be — this is the terminal node) before making
   this change; if you find one, flag it rather than guessing.

### Step 5 — Integrate into `backend/agents/lead_hunter_synthesis.py` (#6)

Per Section 4 of the review:

1. Change `generate_final_report_llm`'s signature to accept an optional
   `cache=None` parameter, defaulting to rebuilding from
   `state.get("investigation_graph")` only if not provided — the caller in
   Step 4 now passes the already-mutated cache directly so the in-memory
   escalations aren't lost by rebuilding from stale state.
2. Import `build_escalation_context` from `verdict_engine` and call it to
   build an `escalation_context` string; inject it into the `context` f-string
   passed to the LLM alongside the existing triage/specialist/graph sections.
3. In `_compute_node_details`, prefer `data.get("composite_verdict")` over the
   raw `gti_assessment` verdict when populating each node's `"verdict"` field,
   while also keeping the original GTI verdict available under a separate key
   (e.g. `"gti_verdict"`) so nothing downstream loses the baseline.
4. Add the "Verdict Handling" paragraph to `LEAD_HUNTER_SYNTHESIS_PROMPT` as
   given in the review, instructing the model to state both the GTI baseline
   and the escalated assessment when they differ, and to surface
   `stale_analysis_days` when present.

### Step 6 — Ordering sanity check

Re-read Section 4's "Ordering constraint" note. Confirm the final call
sequence inside the synthesis branch is:

```
apply_composite_verdicts(cache)
  -> generate_final_report_llm(state, llm_pro, cache=cache)
       -> (internally calls build_escalation_context(cache))
  -> validate_and_annotate(report, cache, ...)
```

If `build_escalation_context` is ever called before `apply_composite_verdicts`
in any code path, it will return a warning string instead of real escalation
data (this is intentional defensive behavior in the module, not a bug to fix)
— but it means you got the ordering wrong somewhere upstream. Trace it back
rather than treating the warning string as acceptable output.

### Step 7 — Run existing test suite

Run whatever test command this repo already uses (check
`cloudbuild-backend.yaml` for the pytest invocation) to confirm nothing
existing broke:

```bash
pytest backend/tests
```

### Step 8 — Summarize

At the end, give me:
- A list of every file you created or modified
- Confirmation that all 53 new tests plus the existing suite pass
- Any places where the real code's shape differed from what the review
  document assumed, and how you resolved it
- Any `# TODO` you left behind and why
- The exact diff-worthy changes to `TRIAGE_ANALYSIS_PROMPT` and
  `LEAD_HUNTER_SYNTHESIS_PROMPT` so I can review the prompt wording separately
  from the code logic

## Guardrails

- Do not touch `backend/utils/graph_cache.py` logic itself — only read from it.
- Do not remove the three existing early-exit layers in `lead_hunter_node`
  (no-uninvestigated-nodes, LLM-signals-complete, convergence-detection) —
  the new code is additive, inserted only in the synthesis branch they fall
  through to.
- Do not weaken the "never downgrade" invariant or the benign/no-signal
  distinction in `verdict_engine.py` even if it seems like it would simplify
  the ladder — both were added specifically to fix false-positive bugs found
  during testing (see review Section 3.1).
- Do not skip Step 2 (standalone tests) before starting integration — you want
  a known-good baseline before touching the live agent files.
- If any repo file's actual structure meaningfully diverges from what's
  described in the review (e.g. `lead_hunter_node`'s synthesis branch has
  since been refactored), stop and describe the discrepancy rather than
  guessing at how to reconcile it.
