"""
Triage signal filtering with heuristic bypasses.

The original filter was purely detection-count based:
    verdict in {malicious, suspicious} OR malicious_vendor_count >= 3

That drops exactly the entities threat hunters care most about. A freshly
registered C2 domain, staged infrastructure, or a targeted first-seen sample
has ZERO detections by construction — the whole point of new infrastructure is
that nobody has flagged it yet.

This module returns a *reason string* rather than a bool, so the surviving
entity can carry `signal_reason` into LLM context. The analyst-model then knows
WHY a zero-detection domain is in front of it, instead of assuming it must
have been flagged.

NOTE: heuristics need full GTI attributes (creation_date, first_submission_date,
last_https_certificate), which are NOT present in the slim `parsed` projection
used for LLM context. Callers must pass `full_attrs`.
"""

import time
from typing import Any, Dict, Optional, Set

from backend.utils.graph_cache import InvestigationCache, _normalise_id, normalize_verdict
from backend.utils.logger import get_logger

logger = get_logger("signal_filter")

SIGNAL_MALICIOUS_VENDORS = 3
RECENCY_WINDOW_DAYS = 30
RARE_SAMPLE_SUBMISSIONS = 3

# TLDs disproportionately represented in abuse data. Only used as a *supporting*
# signal (requires >=1 detection) — never on its own, or every legitimate .xyz
# startup domain floods the graph.
SUSPICIOUS_TLDS = {
    "top", "xyz", "icu", "cyou", "rest", "sbs", "cfd", "click",
    "pw", "gq", "ml", "cf", "tk", "buzz", "monster", "quest",
}


def _epoch(value: Any) -> Optional[float]:
    """GTI returns epoch ints; guard against None / str / 0."""
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def _days_ago(epoch_ts: float, now: float) -> int:
    return int((now - epoch_ts) / 86400)


def get_signal_reason(
    entity_type: str,
    full_attrs: Dict[str, Any],
    verdict: Optional[str],
    malicious_count: int,
    now: Optional[float] = None,
) -> Optional[str]:
    """
    Returns a reason string if the entity is high-signal, else None.

    Rules are ordered strongest-first so the reason attached to the entity is
    the most compelling one, not merely the first that happened to match.
    """
    now = now or time.time()
    cutoff = now - (RECENCY_WINDOW_DAYS * 86400)
    etype = (entity_type or "").lower()

    # --- Existing detection-based rules (strongest) ---
    norm_verdict = normalize_verdict(verdict)
    if norm_verdict in {"malicious", "suspicious"}:
        return f"gti_verdict:{norm_verdict}"
    if (malicious_count or 0) >= SIGNAL_MALICIOUS_VENDORS:
        return f"vendor_detections:{malicious_count}"

    # --- Heuristic bypasses: zero-detection entities that still matter ---

    if etype == "domain":
        # Newly registered domain: the classic staged-C2 signature.
        creation = _epoch(full_attrs.get("creation_date"))
        if creation and creation > cutoff:
            return f"newly_registered:{_days_ago(creation, now)}d"

        # Suspicious TLD *with* at least one detection. Supporting signal only.
        tld = str(full_attrs.get("tld", "")).lower().lstrip(".")
        if tld in SUSPICIOUS_TLDS and (malicious_count or 0) >= 1:
            return f"suspicious_tld:{tld}+detections:{malicious_count}"

        # First seen very recently in passive DNS.
        first_seen = _epoch(full_attrs.get("first_seen_itw_date"))
        if first_seen and first_seen > cutoff:
            return f"recently_first_seen:{_days_ago(first_seen, now)}d"

    elif etype == "file":
        # Fresh AND rare: targeted samples are submitted once or twice, ever.
        first_sub = _epoch(full_attrs.get("first_submission_date"))
        times_submitted = full_attrs.get("times_submitted")
        if (
            first_sub
            and first_sub > cutoff
            and isinstance(times_submitted, int)
            and times_submitted <= RARE_SAMPLE_SUBMISSIONS
        ):
            return f"fresh_rare_sample:{times_submitted}_submissions"

        # Sandbox detonation behaviour on an undetected file is worth a look.
        if full_attrs.get("sandbox_verdicts") or full_attrs.get("behaviour_summary"):
            return "sandbox_behavior_present"

    elif etype == "ip_address":
        # Self-signed cert on a bare IP: strong staging indicator.
        cert = full_attrs.get("last_https_certificate") or {}
        if isinstance(cert, dict) and cert:
            issuer_o = (cert.get("issuer") or {}).get("O")
            subject_o = (cert.get("subject") or {}).get("O")
            if issuer_o and issuer_o == subject_o:
                return "self_signed_cert"

    elif etype == "url":
        first_sub = _epoch(full_attrs.get("first_submission_date"))
        if first_sub and first_sub > cutoff:
            return f"recently_submitted_url:{_days_ago(first_sub, now)}d"

    return None


def promote_by_graph_context(
    cache: InvestigationCache,
    filtered_out: Dict[str, Dict[str, Any]],
    flagged_ids: Set[str],
) -> Dict[str, str]:
    """
    Second pass: an entity that resolves to / is contacted by an already-flagged
    node is high-signal regardless of its own detection count.

    Cannot be done per-entity because it needs a connected graph. Triage only
    creates root->entity edges (star topology), so this runs at Lead Hunter
    synthesis time, after specialists have added entity-entity edges. Pure
    in-memory pass — everything is already in the NetworkX cache by this point.

    Args:
        filtered_out: {entity_id: parsed_entity} that FAILED the per-entity filter
        flagged_ids:  normalised ids of entities that PASSED

    Returns: {entity_id: reason} for entities that should be promoted.
    """
    promoted = {}
    # Graph nodes are stored under normalised (lowercased) ids; normalise both
    # sides so a raw mixed-case caller id can't silently miss every membership
    # check and intersection. Returned keys stay as the caller's original keys.
    norm_flagged = {n for n in (_normalise_id(f) for f in flagged_ids) if n}
    for entity_id in filtered_out:
        norm_id = _normalise_id(entity_id)
        if not norm_id or norm_id not in cache.graph:
            continue
        neighbors = set(cache.graph.successors(norm_id)) | set(
            cache.graph.predecessors(norm_id)
        )
        connected = neighbors & norm_flagged
        if connected:
            sample = sorted(connected)[:2]
            promoted[entity_id] = (
                f"graph_context:connected_to_flagged({','.join(sample)})"
            )
    if promoted:
        logger.info("signal_filter_graph_promotions", count=len(promoted))
    return promoted


def build_promotion_context(cache: InvestigationCache, limit: int = 10) -> str:
    """
    Render graph-context promotions for the synthesis prompt so the LLM can
    weigh them the way an analyst would, instead of dismissing a zero-detection
    entity as benign. Mirrors verdict_engine.build_escalation_context's style.

    Pure/read-only: scans `signal_reason` node attributes written by
    promote_by_graph_context() (called by lead_hunter.py before synthesis).
    Never raises — a rendering failure here must not break report generation.
    """
    try:
        promoted = [
            (node_id, data)
            for node_id, data in cache.graph.nodes(data=True)
            if str(data.get("signal_reason", "")).startswith("graph_context:")
        ]
        if not promoted:
            return "No entities were promoted by graph-context analysis."

        lines = [
            "The following low/zero-detection entities were promoted for analyst "
            "attention because the investigation graph connects them to flagged "
            "infrastructure. Weigh them in the narrative; do not treat their low "
            "detection counts as evidence of benignity:"
        ]
        for node_id, data in promoted[:limit]:
            lines.append(
                f"- {node_id} ({data.get('entity_type', 'unknown')}): "
                f"{data.get('signal_reason')}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error("build_promotion_context_failed", error=str(e))
        return "No entities were promoted by graph-context analysis."

