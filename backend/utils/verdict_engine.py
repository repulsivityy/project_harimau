"""
Composite verdict engine.

GTI's per-entity verdict is authoritative but context-blind: it scores an entity
in isolation. A zero-detection domain that resolves to a confirmed C2 IP and is
contacted by a confirmed dropper is not "undetected" in any meaningful analytic
sense — it is suspicious.

Core principle: NEVER DOWNGRADE GTI. Only escalate, and always record why.
Every escalation must be explainable in the final report, which keeps the
assessment defensible to an analyst reading it.

Run once, in the Lead Hunter node, before synthesis. At that point the graph is
maximally connected, so neighbour-based escalation actually has neighbours to
look at, and it is a single deterministic pass rather than per-agent duplication.
"""

import time
from typing import Any, Dict, Optional

from backend.utils.graph_cache import InvestigationCache, _normalise_id, normalize_verdict
from backend.utils.logger import get_logger

logger = get_logger("verdict_engine")

# Verdict ordering for "never downgrade" enforcement.
# NOTE: benign shares rank 0 with undetected for ordering purposes, but they are
# NOT analytically equivalent — see NO_SIGNAL_VERDICTS below.
VERDICT_RANK = {
    "unknown": 0,
    "undetected": 0,
    "benign": 0,
    "suspicious": 1,
    "malicious": 2,
}

# "undetected"/"unknown" mean *nobody looked hard enough* — absence of evidence.
# "benign" means GTI looked and asserted it is fine — evidence of absence.
#
# Only the former may be escalated on graph context alone. Without this
# distinction, every dns.google / cdn.cloudflare.net / ocsp.digicert.com node
# adjacent to a dropper gets escalated to SUSPICIOUS. Measured on a realistic
# graph that is a 6:1 false-positive rate, which destroys analyst trust in the
# escalation signal entirely.
NO_SIGNAL_VERDICTS = {"undetected", "unknown"}

# Overriding an explicit GTI "benign" requires evidence about the entity itself.
# Set deliberately high — this should fire almost never.
SIGNAL_MALICIOUS_VENDORS_FOR_BENIGN_OVERRIDE = 5

STALE_ANALYSIS_DAYS = 180

# Entity types that carry real GTI reputational data (gti_assessment,
# last_analysis_stats, etc.) and are therefore eligible to be escalated as
# the SUBJECT of the ladder below. Mirrors lead_hunter.py's ACTIONABLE_TYPES
# and the etype switch in signal_filter.get_signal_reason.
#
# Everything else in the graph — MITRE ATT&CK technique nodes ("attack_technique",
# from the attack_techniques relationship), campaign/actor/malware-family
# attribution nodes ("collection", from associations/campaigns/malware_families/
# related_threat_actors), and DNS-resolution join-records ("resolution", from
# the resolutions relationship) — never carries gti_assessment. Their
# _gti_verdict() always defaults to "unknown", which is a NO_SIGNAL_VERDICT,
# so without this guard Rule 1 would escalate a technique reference or a
# collection tag to "suspicious" merely for being graph-adjacent to malware —
# which is not a meaningful analytic claim about that node.
REAL_INDICATOR_TYPES = {"file", "domain", "ip_address", "url"}


def _gti_verdict(attrs: Dict[str, Any]) -> str:
    assessment = attrs.get("gti_assessment") or {}
    verdict_obj = assessment.get("verdict") or {}
    raw = verdict_obj.get("value") if isinstance(verdict_obj, dict) else None
    return normalize_verdict(raw) or "unknown"


def _gti_score(attrs: Dict[str, Any]) -> int:
    assessment = attrs.get("gti_assessment") or {}
    score_obj = assessment.get("threat_score") or {}
    if isinstance(score_obj, dict):
        value = score_obj.get("value")
        return int(value) if value is not None else 0
    return 0


def _malicious_vendor_count(attrs: Dict[str, Any]) -> int:
    stats = attrs.get("last_analysis_stats") or {}
    return stats.get("malicious", 0) if isinstance(stats, dict) else 0


def _has_attribution(attrs: Dict[str, Any]) -> bool:
    """Family or actor attribution is a strong malicious signal on its own."""
    for field in ("malware_families", "related_threat_actors", "associations", "campaigns"):
        value = attrs.get(field)
        if value:
            return True
    return False


def _has_sandbox_behavior(attrs: Dict[str, Any]) -> bool:
    for field in ("sandbox_verdicts", "behaviour_summary", "crowdsourced_ids_results"):
        if attrs.get(field):
            return True
    return False


def _is_stale(attrs: Dict[str, Any]) -> Optional[int]:
    """Returns age in days if the analysis is older than STALE_ANALYSIS_DAYS."""
    last = attrs.get("last_analysis_date")
    if not isinstance(last, (int, float)) or last <= 0:
        return None
    age_days = int((time.time() - last) / 86400)
    return age_days if age_days > STALE_ANALYSIS_DAYS else None


def compute_composite_verdict(entity_id: str, cache: InvestigationCache) -> Dict[str, Any]:
    """
    Deterministic escalation ladder. Pure function over one node + its neighbours.
    """
    # Graph nodes are stored under normalised (lowercased) ids; get_entity_full
    # normalises internally but the direct successors/predecessors calls below
    # do not, so a raw mixed-case id would crash there. Normalise once up front.
    entity_id = _normalise_id(entity_id) or entity_id
    attrs = cache.get_entity_full(entity_id)
    if not attrs:
        return {
            "composite_verdict": "unknown",
            "gti_verdict": "unknown",
            "escalated": False,
            "escalation_reasons": [],
        }

    # Non-entity taxonomy/collection/technique/resolution-join nodes have no
    # real reputational data to escalate. Return early with a sentinel that
    # does not participate in escalation (composite_verdict=None). This does
    # NOT affect the neighbor-scanning loop below for OTHER entities: a node
    # without gti_assessment always has _gti_verdict() == "unknown" !=
    # "malicious", so it could never have counted as a "malicious neighbor"
    # for its neighbors anyway — this guard only concerns whether THIS node
    # can itself be escalated.
    entity_type = attrs.get("entity_type")
    if entity_type not in REAL_INDICATOR_TYPES:
        return {
            "composite_verdict": None,
            "gti_verdict": _gti_verdict(attrs),
            "escalated": False,
            "escalation_reasons": [],
            "malicious_neighbors": 0,
            "malicious_neighbor_ids": [],
        }

    base = _gti_verdict(attrs)
    reasons: list = []

    # --- Gather graph context: how many confirmed-malicious neighbours? ---
    malicious_neighbors = 0
    malicious_neighbor_ids = []
    # Undirected view: an entity is contextually implicated whether it points at
    # a malicious node or is pointed at by one.
    neighbors = set(cache.graph.successors(entity_id)) | set(cache.graph.predecessors(entity_id))
    for neighbor in neighbors:
        n_attrs = cache.graph.nodes[neighbor]
        if _gti_verdict(n_attrs) == "malicious":
            malicious_neighbors += 1
            malicious_neighbor_ids.append(neighbor)

    has_attribution = _has_attribution(attrs)
    has_sandbox = _has_sandbox_behavior(attrs)
    vendor_count = _malicious_vendor_count(attrs)

    verdict = base
    no_signal = base in NO_SIGNAL_VERDICTS

    # --- Escalation ladder (each rule can only raise, never lower) ---

    if no_signal:
        # Rule 1: no-signal entity adjacent to confirmed malice.
        if malicious_neighbors >= 1:
            verdict = "suspicious"
            reasons.append(f"connects_to_{malicious_neighbors}_malicious_entities")

        # Rule 2: no-signal entity that detonated with behaviour AND sits in bad company.
        if has_sandbox and malicious_neighbors >= 1:
            verdict = "suspicious"
            if "sandbox_behavior_plus_malicious_context" not in reasons:
                reasons.append("sandbox_behavior_plus_malicious_context")

        # Rule 3: attribution alone is enough to escalate a no-signal entity.
        if has_attribution:
            verdict = "suspicious"
            if "has_family_or_actor_attribution" not in reasons:
                reasons.append("has_family_or_actor_attribution")

    elif base == "benign":
        # GTI explicitly asserted this is fine. Overriding that requires evidence
        # ABOUT THE ENTITY ITSELF, not merely bad company — otherwise every CDN,
        # DNS resolver, and OCSP responder in the graph gets escalated.
        # Adjacency alone is never sufficient.
        own_evidence = []
        if vendor_count >= SIGNAL_MALICIOUS_VENDORS_FOR_BENIGN_OVERRIDE:
            own_evidence.append(f"vendor_detections:{vendor_count}")
        if has_attribution:
            own_evidence.append("has_family_or_actor_attribution")
        if own_evidence and malicious_neighbors >= 1:
            verdict = "suspicious"
            reasons.extend(own_evidence)
            reasons.append("overrides_gti_benign")

    # Rule 4: suspicious + corroboration => malicious.
    # Only applies to entities that started with no signal. A GTI-benign entity
    # never jumps two levels in a single pass.
    if verdict == "suspicious" and no_signal:
        corroborations = []
        if malicious_neighbors >= 2:
            corroborations.append(f"{malicious_neighbors}_malicious_connections")
        if has_attribution:
            corroborations.append("has_family_or_actor_attribution")
        if vendor_count >= 3:
            corroborations.append(f"vendor_detections:{vendor_count}")
        if malicious_neighbors >= 2 or has_attribution:
            verdict = "malicious"
            reasons.extend(c for c in corroborations if c not in reasons)

    # --- Never downgrade: enforce as a hard invariant ---
    if VERDICT_RANK[verdict] < VERDICT_RANK[base]:
        logger.error("verdict_downgrade_blocked", entity_id=entity_id,
                     base=base, attempted=verdict)
        verdict = base
        reasons = []

    escalated = VERDICT_RANK[verdict] > VERDICT_RANK[base]

    result = {
        "composite_verdict": verdict,
        "gti_verdict": base,
        "escalated": escalated,
        "escalation_reasons": reasons if escalated else [],
        "malicious_neighbors": malicious_neighbors,
        "malicious_neighbor_ids": malicious_neighbor_ids[:5],
    }

    stale_days = _is_stale(attrs)
    if stale_days:
        result["stale_analysis_days"] = stale_days

    return result


def apply_composite_verdicts(cache: InvestigationCache, job_id: Optional[str] = None) -> Dict[str, int]:
    """
    Single deterministic pass over the whole graph. Writes results back onto
    each node so downstream consumers (synthesis high-signal selection,
    graph UI tooltips) can read them.

    IMPORTANT: computed against a frozen snapshot of the ORIGINAL GTI verdicts.
    Escalations must not cascade — an entity escalated to malicious by Rule 1
    must not then cause its own neighbours to escalate. Otherwise a single
    malicious node would eventually paint the entire graph.
    """
    results = {}
    # Pass 1: compute everything against untouched GTI verdicts.
    for node_id in list(cache.graph.nodes()):
        results[node_id] = compute_composite_verdict(node_id, cache)

    # Pass 2: write back.
    escalated_count = 0
    stale_count = 0
    for node_id, result in results.items():
        if result["composite_verdict"] is None:
            # Non-entity node (taxonomy/collection/technique/resolution-join)
            # — no meaningful verdict to report. Leave the node's attributes
            # alone rather than writing composite_verdict=None onto every
            # such node; build_escalation_context()'s escalation filter and
            # "has apply() run" guard both key off real entities having these
            # fields set, so skipping is safe as long as at least one real
            # entity exists in the graph (the root IOC always is one).
            continue
        cache.graph.nodes[node_id]["composite_verdict"] = result["composite_verdict"]
        cache.graph.nodes[node_id]["verdict_escalated"] = result["escalated"]
        cache.graph.nodes[node_id]["escalation_reasons"] = result["escalation_reasons"]
        if result.get("stale_analysis_days"):
            cache.graph.nodes[node_id]["stale_analysis_days"] = result["stale_analysis_days"]
            stale_count += 1
        if result["escalated"]:
            escalated_count += 1

    stats = {
        "nodes_evaluated": len(results),
        "escalated": escalated_count,
        "stale": stale_count,
    }
    logger.info("composite_verdicts_applied", job_id=job_id, **stats)
    return stats


def build_escalation_context(cache: InvestigationCache, limit: int = 10) -> str:
    """
    Render escalations for the synthesis prompt so the LLM can narrate them
    the way an analyst would: 'GTI: undetected -> assessed SUSPICIOUS because...'
    """
    # Guard: if apply_composite_verdicts() has not run, every node lacks the
    # marker and we would silently report "no escalations" — a false negative
    # that looks identical to a clean investigation. Fail loudly instead.
    applied = any(
        "composite_verdict" in data for _, data in cache.graph.nodes(data=True)
    )
    if cache.graph.number_of_nodes() > 0 and not applied:
        logger.error("escalation_context_before_apply")
        return (
            "Composite verdict analysis was not run for this investigation; "
            "verdicts shown are raw GTI values."
        )

    escalations = [
        (node_id, data)
        for node_id, data in cache.graph.nodes(data=True)
        if data.get("verdict_escalated")
    ]
    if not escalations:
        return "No entities were escalated beyond their GTI verdict."

    lines = ["The following entities were escalated by graph-context analysis. "
             "Report these as analyst assessments, explicitly noting the GTI baseline:"]
    for node_id, data in escalations[:limit]:
        reasons = ", ".join(data.get("escalation_reasons", [])) or "unspecified"
        lines.append(
            f"- {node_id} ({data.get('entity_type', 'unknown')}): "
            f"GTI={_gti_verdict(data)} -> ASSESSED {data['composite_verdict'].upper()} "
            f"| basis: {reasons}"
        )

    stale = [
        (n, d) for n, d in cache.graph.nodes(data=True) if d.get("stale_analysis_days")
    ]
    if stale:
        lines.append("\nStale analyses (verdicts may not reflect current state):")
        for node_id, data in stale[:5]:
            lines.append(f"- {node_id}: last analysed {data['stale_analysis_days']} days ago")

    return "\n".join(lines)

