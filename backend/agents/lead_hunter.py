# Active orchestrator for Project Harimau: calls run_planning_phase + generate_final_report_llm (do not delete or supersede).
import os
#from langchain_google_vertexai import ChatVertexAI
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import DEFAULT_HUNT_ITERATIONS
from backend.graph.state import AgentState
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache

from backend.agents.lead_hunter_planning import run_planning_phase
from backend.agents.lead_hunter_synthesis import generate_final_report_outcome
from backend.utils.verdict_engine import apply_composite_verdicts
from backend.utils.report_validator import validate_and_annotate
from backend.utils.signal_filter import promote_by_graph_context
from backend.utils.transparency import emit_reasoning
from backend.utils.target_outcomes import canonical_agent, normalise_target_id

logger = get_logger("agent_lead_hunter")

ACTIONABLE_TYPES = {"file", "ip_address", "domain", "url"}


def _unresolved_target_outcomes(state: AgentState):
    """Return retryable target failures from the latest specialist attempts."""
    return [
        outcome for outcome in (state.get("target_outcomes") or {}).values()
        if outcome.get("status") != "succeeded" and outcome.get("target_id") and outcome.get("agent")
    ]


async def lead_hunter_node(state: AgentState):
    """
    Lead Threat Hunter Node.
    - Iteration < Max: Plan next steps (generate subtasks).
    - Iteration >= Max OR early exit condition met: Synthesize final report.

    Early exit conditions (in order):
      Layer 1 - No uninvestigated actionable nodes remain (zero-cost, no LLM call).
      Layer 2 - LLM signals investigation_complete in its planning response.
      Layer 3 - New subtasks are a subset of actually processed entities
                (convergence). Scheduled-but-capped targets remain eligible.
    """
    logger.info("lead_hunter_start", iteration=state.get("iteration"))

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")

    # Flash for planning (fast, cost-efficient), Pro only for final synthesis
    # llm_flash = ChatVertexAI(
    #     model="gemini-2.5-flash",
    #     temperature=0.1,
    #     project=project_id,
    #     location=location,
    # )
    # llm_pro = ChatVertexAI(
    #     model="gemini-2.5-pro",
    #     temperature=0.1,
    #     project=project_id,
    #     location="global",
    # )
    llm_flash = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        temperature=0.1,
        #max_tokens=1024,
        project=project_id,
        location="global",
        #vertexai=True,  # Explicitly use Vertex AI
    )
    llm_pro = ChatGoogleGenerativeAI(
        model="gemini-3.1-pro-preview",
        temperature=0.1,
        #max_tokens=1024,
        project=project_id,
        location="global",
        #vertexai=True,  # Explicitly use Vertex AI
    )

    # Initialize Cache to read graph state
    cache = InvestigationCache(state.get("investigation_graph"))

    # --- DETERMINE MODE ---
    job_id = state.get("job_id")
    current_iteration = state.get("iteration", 0)
    MAX_ITERATIONS = state.get("max_iterations", DEFAULT_HUNT_ITERATIONS)

    # A prior stage may have produced a readable fallback report while failing
    # to establish coverage (for example GTI enrichment). Do not turn that
    # into a successful convergence or synthesize over it.
    prior_outcome = state.get("investigation_outcome") or (state.get("metadata") or {}).get("investigation_outcome")
    if prior_outcome and prior_outcome.get("status") == "failed":
        logger.error("lead_hunter_prior_stage_failed", job_id=job_id, outcome=prior_outcome)
        if job_id:
            await emit_reasoning(
                job_id,
                "lead_hunter",
                f"TERMINAL_FAILURE -> {prior_outcome.get('stage', 'unknown stage')} failed; investigation coverage is unknown.",
            )
        return {
            "final_report": state.get("final_report") or "# Investigation Failed\n\nCoverage could not be established.",
            "subtasks": [],
            "investigation_outcome": prior_outcome,
        }

    if current_iteration < MAX_ITERATIONS:
        # --- LAYER 1: Pre-check uninvestigated nodes (no LLM call needed) ---
        uninvestigated = cache.get_uninvestigated_nodes()
        actionable = [n for n in uninvestigated if n.get("entity_type") in ACTIONABLE_TYPES]

        unresolved_outcomes = _unresolved_target_outcomes(state)
        if not actionable and not unresolved_outcomes:
            logger.info("lead_hunter_early_exit", reason="no_uninvestigated_nodes", iteration=current_iteration)
        else:
            # --- PLANNING MODE (uses Flash) ---
            logger.info("lead_hunter_mode_planning", actionable_count=len(actionable))

            plan = await run_planning_phase(state, llm_flash, cache, actionable)
            planning_outcome = plan.get("outcome") or {}
            if planning_outcome.get("status") == "failed":
                logger.error("lead_hunter_planning_terminal_failure", job_id=job_id, outcome=planning_outcome)
                if job_id:
                    await emit_reasoning(
                        job_id,
                        "lead_hunter_planning",
                        "TERMINAL_FAILURE -> Planning failed; investigation coverage is unknown and synthesis was not attempted.",
                    )
                error = planning_outcome.get("error") or "Lead Hunter planning failed"
                return {
                    "final_report": f"# Investigation Failed\n\nPlanning could not determine next steps. Error: {error}",
                    "subtasks": [],
                    "investigation_outcome": planning_outcome,
                }
            new_subtasks = plan.get("subtasks", [])

            # --- LAYER 2: LLM confidence signal ---
            if plan.get("investigation_complete") and not unresolved_outcomes:
                logger.info("lead_hunter_early_exit", reason="llm_signals_complete", iteration=current_iteration)
                new_subtasks = []
            elif plan.get("investigation_complete"):
                logger.info(
                    "lead_hunter_completion_deferred_unresolved_targets",
                    unresolved_count=len(unresolved_outcomes),
                )

            # A model may omit a failed lead or incorrectly report completion.
            # Put retries first, and mark them for the specialist selectors, so
            # a full planner batch cannot consume the specialist cap first.
            retry_subtasks = []
            retry_keys = set()
            for outcome in unresolved_outcomes:
                agent = canonical_agent(outcome.get("agent"))
                target_id = normalise_target_id(outcome.get("target_id"))
                if not agent or not target_id or (agent, target_id) in retry_keys:
                    continue
                retry_subtasks.append({
                    "agent": f"{agent}_specialist",
                    "entity_id": target_id,
                    "task": "Retry target-specific specialist analysis",
                    "context": f"Unresolved gap from prior attempt: {outcome.get('reason') or 'insufficient evidence'}.",
                    "priority": "retry",
                })
                retry_keys.add((agent, target_id))

            # A planner task for the same specialist/target is represented by
            # the deterministic retry above. Canonical aliases prevent both
            # spellings from using a slot.
            planned_subtasks = [
                task for task in new_subtasks
                if (canonical_agent(task.get("agent")), normalise_target_id(task.get("entity_id"))) not in retry_keys
            ]
            new_subtasks = [*retry_subtasks, *planned_subtasks]

            if new_subtasks:
                # --- LAYER 3: Convergence detection ---
                # A target can be scheduled during triage or a prior planning
                # round yet be deferred by a specialist cap (five malware
                # targets / ten infrastructure targets). Treating scheduled
                # entities as completed here drops those deferred leads. Older
                # checkpoints simply lack processed_entities; an empty set is
                # safe because the graph's investigated marker still removes
                # completed nodes from the planner input.
                previously_processed = {
                    str(e).strip().lower()
                    for e in (state.get("processed_entities") or [])
                    if e
                }

                # A planner can repeat previously processed targets alongside a
                # deferred target. Passing that mixed batch through unchanged
                # lets repeated targets consume a specialist's per-pass cap and
                # starve the deferred lead. Keep only unresolved targets before
                # dispatch, retaining the planner's order for deterministic caps.
                dispatchable_subtasks = []
                scheduled_ids = []
                seen_scheduled_ids = set()
                for task in new_subtasks:
                    entity_id = task.get("entity_id")
                    normalized_id = str(entity_id).strip().lower() if entity_id else None
                    if normalized_id and normalized_id in previously_processed:
                        continue
                    dispatchable_subtasks.append(task)
                    if normalized_id and normalized_id not in seen_scheduled_ids:
                        scheduled_ids.append(normalized_id)
                        seen_scheduled_ids.add(normalized_id)

                if len(dispatchable_subtasks) != len(new_subtasks):
                    logger.info(
                        "lead_hunter_processed_tasks_removed",
                        removed=len(new_subtasks) - len(dispatchable_subtasks),
                    )
                new_subtasks = dispatchable_subtasks

                if new_subtasks:
                    logger.info("lead_hunter_new_tasks", count=len(new_subtasks))
                    # Emitted here, not in run_planning_phase: only at this point
                    # have Layers 2 and 3 confirmed the planner's subtasks will
                    # actually be dispatched rather than discarded.
                    if job_id:
                        subtask_summary = [
                            f"CONVERGENCE_DECISION -> Initiating Iteration {current_iteration + 1} "
                            f"with {len(new_subtasks)} subtask(s):"
                        ]
                        for t in new_subtasks:
                            subtask_summary.append(f"  • [{t.get('agent')}] {t.get('entity_id')}: {t.get('task')}")
                        await emit_reasoning(job_id, "lead_hunter_planning", "\n".join(subtask_summary))
                    return {
                        "subtasks": new_subtasks,
                        "iteration": current_iteration + 1,
                        "scheduled_entities": scheduled_ids,
                        # Retain the legacy field for persisted state readers.
                        "tasked_entities": scheduled_ids,
                    }

                logger.info(
                    "lead_hunter_early_exit",
                    reason="convergence",
                    entities=sorted(previously_processed),
                )

            logger.info("lead_hunter_no_new_tasks", reason="empty_subtasks_or_converged")
            if job_id:
                await emit_reasoning(
                    job_id,
                    "lead_hunter_planning",
                    "CONVERGENCE_DECISION -> All hypotheses answered or no actionable targets remaining. Terminating planning loop.",
                )

    # --- SYNTHESIS MODE (uses Pro) ---
    logger.info("lead_hunter_mode_synthesis")

    # Graph-context promotion runs here, not in triage. Triage only ever
    # creates root->entity edges (a star topology), so at triage time a
    # dropped entity's only neighbor is the root IOC — which is never
    # "flagged" — so promotion could never fire there. By synthesis time
    # specialists have added entity-entity edges, so the graph is connected
    # enough for adjacency to mean something. See signal_filter.py and
    # triage.py's signal_filter_carryover persistence.
    carryover = (state.get("metadata") or {}).get("rich_intel", {}).get("signal_filter_carryover") or {}
    dropped = carryover.get("dropped_entities") or {}
    flagged = set(carryover.get("flagged_ids") or [])
    if dropped and flagged:
        promoted = promote_by_graph_context(cache, dropped, flagged)
        for entity_id, reason in promoted.items():
            # An entity dropped under one relationship may have survived the
            # filter under another — it's already surfaced, don't re-promote.
            if entity_id in flagged:
                continue
            if entity_id in cache.graph and "signal_reason" not in cache.graph.nodes[entity_id]:
                cache.graph.nodes[entity_id]["signal_reason"] = reason

    # Composite verdicts must be computed before synthesis so the report can
    # narrate graph-context escalations (e.g. undetected domain resolving to a
    # confirmed C2 IP) instead of echoing raw GTI verdicts. See verdict_engine.py.
    apply_composite_verdicts(cache, job_id=state.get("job_id"))

    synthesis_outcome = await generate_final_report_outcome(state, llm_pro, cache=cache)
    final_report = synthesis_outcome["report"]
    if synthesis_outcome.get("status") == "failed":
        logger.error("lead_hunter_synthesis_terminal_failure", job_id=job_id, outcome=synthesis_outcome)
        if job_id:
            await emit_reasoning(
                job_id,
                "lead_hunter_synthesis",
                "TERMINAL_FAILURE -> Final synthesis failed; investigation coverage is unknown.",
            )
        return {
            "final_report": final_report,
            "subtasks": [],
            "investigation_graph": cache.get_state(),
            "investigation_outcome": synthesis_outcome,
        }

    # The iteration budget can force synthesis before a retry succeeds. Keep
    # those failures visible to the analyst instead of allowing a polished
    # final report to imply complete coverage.
    unresolved_outcomes = _unresolved_target_outcomes(state)
    if unresolved_outcomes:
        gap_lines = ["\n## Unresolved Specialist Gaps\n"]
        gap_lines.append("The following targets were not marked investigated and require a retry:\n")
        for outcome in unresolved_outcomes:
            gap_lines.append(
                f"- `{outcome['target_id']}` ({outcome['agent']}): "
                f"{outcome.get('reason') or 'insufficient target-specific evidence'}\n"
            )
        final_report += "".join(gap_lines)

    # Annotate (never strip) any IOC cited in the report that isn't grounded in
    # the investigation graph or specialist findings. See report_validator.py.
    final_report, validation = validate_and_annotate(
        report_md=final_report,
        cache=cache,
        specialist_results=state.get("specialist_results", {}),
        root_ioc=state.get("ioc"),
        job_id=state.get("job_id"),
    )
    if job_id:
        # The trace must report what the audit actually found — a hardcoded
        # success message would claim verification even when citations failed.
        verified_count = validation.get("verified", 0)
        unverified_count = len(validation.get("unverified") or [])
        if validation.get("error"):
            audit_message = (
                "CITATION_AUDIT -> Citation verification could not be completed; "
                "report IOC citations are UNAUDITED."
            )
        elif unverified_count:
            audit_message = (
                f"CITATION_AUDIT -> Verified {verified_count} indicator(s) against the NetworkX "
                f"investigation graph cache; {unverified_count} unverified/hallucinated "
                f"citation(s) flagged in the report."
            )
        else:
            audit_message = (
                f"CITATION_AUDIT -> Verified all {verified_count} report IOC citation(s) "
                f"against the NetworkX investigation graph cache."
            )
        await emit_reasoning(job_id, "lead_hunter_synthesis", audit_message)

    # [CRITICAL] CLEAR SUBTASKS TO STOP INFINITE LOOP
    # investigation_graph IS now mutated (graph-context promotions and
    # composite verdicts written onto nodes above), so it must be
    # returned/persisted here or those annotations are lost. This is the
    # terminal node with no parallel writer at this point, so merge_graphs is
    # not a concern.
    return {
        "final_report": final_report,
        "subtasks": [],
        "investigation_graph": cache.get_state(),
    }
