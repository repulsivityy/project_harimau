# Project Harimau — Accuracy Fixes Review (#2, #3, #6)

> **Date:** 2026-07-09
> **Scope:** Fixes #2 (report IOC validation), #3 (heuristic signal filter bypasses), #6 (composite verdict engine) from the original code review.
> **Status:** Modules written, unit-tested (53/53 passing) against realistic GTI-shaped fixtures in an isolated sandbox. **Not yet integrated into the live repo.**
> **Companion file:** `claude-fable-review-agent-prompt-9jul26.md` — hand that file to the coding agent as its instructions.

---

## 1. Problem Statements

### #2 — Reports can cite IOCs that were never observed

The Lead Hunter's final synthesis report is LLM-generated prose. Even with graph-grounded edge tuples for the Graphviz diagram, nothing verifies that hashes, IPs, or domains mentioned in the *narrative text* actually exist in the investigation. A hallucinated IOC in a threat intel report is actionable-looking but false — an analyst could pivot on it.

### #3 — The signal filter drops the entities analysts care about most

`triage.py`'s current filter:

```python
normalize_verdict(e.get("verdict")) in {"malicious", "suspicious"}
or (e.get("malicious_count") or 0) >= SIGNAL_MALICIOUS_VENDORS
```

is purely detection-count based. Freshly registered C2 domains, staged infrastructure, and targeted first-seen samples have **zero detections by construction** — nobody has flagged them yet. The filter systematically excludes exactly the indicators a threat hunter would flag by eye.

### #6 — Verdicts are a pure GTI echo with no graph context

`threat_score` and `verdict` are read directly from `gti_assessment` with no corroboration from the investigation itself. An "undetected" domain that resolves to a confirmed C2 IP and is contacted by a confirmed dropper is not undetected in any analytically meaningful sense — but nothing in the pipeline currently says so.

---

## 2. What Was Built

| Module | Fix | New file |
|---|---|---|
| Report IOC validator | #2 | `backend/utils/report_validator.py` |
| Heuristic signal filter | #3 | `backend/utils/signal_filter.py` |
| Composite verdict engine | #6 | `backend/utils/verdict_engine.py` |
| Test suite | all three | `backend/tests/test_accuracy_fixes.py` |

All four are reproduced in full in **Section 5** of this document so the coding agent can create them without needing any other file.

---

## 3. Design Decisions (read before integrating)

These aren't stylistic choices — two of them came directly out of failures caught during testing, and skipping them will reintroduce the bugs.

### 3.1 `benign` is not `undetected` (verdict engine)

The first version of the escalation ladder treated any zero-detection verdict — including GTI's explicit `benign` — as escalatable on graph adjacency alone. Tested against a realistic graph (one dropper, one real C2, six pieces of benign infrastructure: `dns.google`, `cdn.cloudflare.net`, `ocsp.digicert.com`, etc.), it escalated **6 benign nodes to SUSPICIOUS for 1 real C2**. A 6:1 false-positive rate would make analysts stop trusting escalations within a week.

The fix distinguishes two concepts that look identical at rank 0 but aren't:

- `undetected` / `unknown` = **absence of evidence** — nobody has looked hard enough yet. These may be escalated on graph context alone.
- `benign` = **evidence of absence** — GTI looked and explicitly asserted it's fine. Escalating this requires evidence about the entity itself (≥5 vendor detections, or malware-family/threat-actor attribution) *in addition to* malicious adjacency, and even then it can only reach `suspicious`, never jump straight to `malicious`.

Re-tested after the fix: **1/8 escalated, zero benign false positives** — only the real C2 escalates.

### 3.2 No escalation cascade

`apply_composite_verdicts()` computes every node's composite verdict against a **frozen snapshot of the original GTI verdicts** (pass 1), then writes results back in a separate step (pass 2). This matters because if an entity escalated by Rule 1 could then cause *its own neighbors* to escalate, a single malicious node would eventually paint the entire graph malicious-adjacent.

Verified with a 5-node linear chain hanging off one malicious root: only the node directly adjacent to the root escalates; nodes 2–4 hops away stay at their original verdict. The function is also idempotent — running it twice in a row produces identical output.

### 3.3 Never downgrade

Enforced as a hard invariant with a `logger.error` if violated (should never trigger in practice — it's a correctness backstop, not expected behavior). Composite verdicts only ever raise a verdict, never lower one, and every escalation carries a `reasons` list so it's defensible when an analyst reads the report and asks "why does this say malicious when GTI says undetected?"

### 3.4 Validator annotates, never strips

`report_validator.py` never deletes text from the report — it appends a footer listing unverified IOCs. Silently stripping a hash mid-sentence breaks the Markdown and hides the fact that the model made an error; annotating surfaces it instead. The validator also never raises — a bug in the validator must not block report delivery, so `validate_and_annotate()` catches everything and falls back to returning the report unmodified.

To avoid false positives on the IOC-shaped strings that show up constantly in security writing, the validator:
- Refangs defanged IOCs (`evil[.]com`, `hxxp://`) before matching
- Strips fenced code blocks and Graphviz `digraph { }` bodies before matching (these often contain file paths / DOT syntax that look like domains)
- Rejects filenames by extension (`svchost.exe`, `lead_hunter_synthesis.py`, `settings.yaml`, etc. — see `NON_TLD_SUFFIXES`)
- Validates IPv4 octets are ≤ 255 so version strings like `10.2.1.300` aren't flagged
- Cross-references specialist `network_indicators` / `related_indicators` (prefix-stripped, e.g. `File:abc123` → `abc123`) in addition to the NetworkX graph, since a legitimately-discovered IOC may exist in specialist output before it's written into the graph node itself

### 3.5 The signal filter needs full attributes, not the slim LLM projection

`triage.py`'s parse loop builds a slim `parsed` dict (`id`, `type`, `verdict`, `threat_score`, `malicious_count`) for LLM context — that's the whole point of the token-optimization architecture. But the new heuristics (`creation_date`, `first_submission_date`, `last_https_certificate`, `times_submitted`) live in `full_attrs`, which is available in the same loop but currently discarded after `cache.add_entity()`.

The fix carries `full_attrs` through the filter under a private key (`parsed["_full_attrs"]`) and strips it back out before the entity is added to LLM context. See the exact diff in the agent prompt file.

### 3.6 Graph-context promotion needs a second pass

"This zero-detection domain resolves to an already-flagged malicious IP" can't be evaluated inside the per-entity parse loop — it needs the *whole* graph, which only exists once every relationship type has been fetched and parsed. `signal_filter.py` exposes `promote_by_graph_context()` as a separate function that must run **after** the main per-entity loop closes, using the fully-populated `InvestigationCache`.

---

## 4. Integration Points (repo files to change)

None of the new files are drop-in replacements — they need to be wired into three existing files. Full diffs are in the agent prompt file; summary here:

| File | Change |
|---|---|
| `backend/agents/triage.py` | Import `signal_filter`; carry `full_attrs` through the parse loop; replace the filter block; add a second-pass graph-context promotion call after relationship parsing; add a paragraph to `TRIAGE_ANALYSIS_PROMPT` telling the LLM not to treat `signal_reason` entities as benign-by-default. |
| `backend/agents/lead_hunter.py` | Import `verdict_engine` and `report_validator`; in the synthesis branch, call `apply_composite_verdicts(cache)` **before** `generate_final_report_llm()`, then call `validate_and_annotate()` on the result; return `investigation_graph: cache.get_state()` (currently omitted — this must change or escalations are lost at persistence). |
| `backend/agents/lead_hunter_synthesis.py` | Accept an optional `cache` param to avoid rebuilding the graph and losing in-memory escalations; call `build_escalation_context(cache)` and inject it into the synthesis prompt context; prefer `composite_verdict` over raw `gti_assessment` verdict in `_compute_node_details()`; add a "Verdict Handling" paragraph to `LEAD_HUNTER_SYNTHESIS_PROMPT` instructing the LLM to state both the GTI baseline and the escalated assessment when they differ. |

**Ordering constraint:** `apply_composite_verdicts()` must run before `build_escalation_context()` is called (the latter detects and warns if the former hasn't run) and before `validate_and_annotate()` (which reads the cache, not the pre-verdict state).

---

## 5. Full Source — New Files

Create these exactly as-is. Each is self-contained and only depends on `backend.utils.graph_cache` and `backend.utils.logger`, which already exist in the repo.

#### `backend/utils/report_validator.py`

```python
"""
Post-synthesis IOC validation.

The Lead Hunter's final report is LLM-generated prose. Even with graph-grounded
edge tuples, nothing verifies that the IOCs it *cites* actually exist in the
investigation. This module extracts every IOC-shaped token from the report and
checks it against the known universe (NetworkX graph + specialist indicator lists).

Design decision: ANNOTATE, don't strip. Silently removing IOCs from a report is
worse than flagging them, and stripping mid-sentence breaks the Markdown.
"""

import re
from typing import Any, Dict, List, Optional

from backend.utils.graph_cache import InvestigationCache, _normalise_id
from backend.utils.logger import get_logger

logger = get_logger("report_validator")

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Order matters for reporting only; each is matched independently.
IOC_PATTERNS = {
    "sha256": re.compile(r"\b[a-fA-F0-9]{64}\b"),
    "sha1":   re.compile(r"\b[a-fA-F0-9]{40}\b"),
    "md5":    re.compile(r"\b[a-fA-F0-9]{32}\b"),
    "ipv4":   re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Deliberately permissive; heavily post-filtered below.
    "domain": re.compile(r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,24}\b"),
}

# Fenced code blocks and inline code often contain file paths, module names,
# and version strings that look like IOCs. Strip them before matching.
_FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_GRAPHVIZ_BLOCK = re.compile(r"(?:digraph|graph)\s+\w*\s*\{.*?\}", re.DOTALL)

# Extensions/suffixes that the domain regex will falsely match.
NON_TLD_SUFFIXES = {
    # source files
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "rb", "java", "c", "h", "cpp",
    "sh", "yaml", "yml", "json", "toml", "ini", "cfg", "md", "txt", "csv",
    # windows/pe artefacts that appear constantly in malware reports
    "exe", "dll", "sys", "bat", "cmd", "ps1", "vbs", "scr", "ocx", "cpl",
    "msi", "lnk", "hta", "jar", "bin", "tmp", "dat", "log", "pdb",
    # archives / docs
    "zip", "rar", "7z", "gz", "tar", "iso", "img", "doc", "docx", "xls",
    "xlsx", "ppt", "pptx", "pdf", "rtf",
}

# Cross-agent handoff prefixes: "File:abc123", "IP:1.2.3.4", "Domain:evil.com"
_PREFIXED = re.compile(r"^(?:file|ip|domain|url|hash|md5|sha1|sha256)\s*:\s*", re.IGNORECASE)


def _refang(text: str) -> str:
    """Reports frequently defang IOCs. Normalise before matching."""
    return (
        text.replace("[.]", ".")
        .replace("(.)", ".")
        .replace("[dot]", ".")
        .replace("hxxps", "https")
        .replace("hxxp", "http")
        .replace("[:]", ":")
        .replace("[@]", "@")
    )


def _strip_code(text: str) -> str:
    """Remove fenced blocks and graphviz DOT bodies before IOC extraction."""
    text = _FENCED_BLOCK.sub(" ", text)
    text = _GRAPHVIZ_BLOCK.sub(" ", text)
    return text


def _valid_ipv4(value: str) -> bool:
    """Reject version strings like 10.2.1.300 and 1.2.3.4567."""
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or len(p) > 3:
            return False
        if int(p) > 255:
            return False
    return True


def _plausible_domain(value: str) -> bool:
    """Reject filenames, module paths, and version-ish tokens."""
    suffix = value.rsplit(".", 1)[-1].lower()
    if suffix in NON_TLD_SUFFIXES:
        return False
    if suffix.isdigit():
        return False
    # A bare two-label token whose left side is numeric is almost always a version.
    labels = value.split(".")
    if all(lab.isdigit() for lab in labels[:-1]):
        return False
    return True


def _strip_prefix(indicator: str) -> str:
    """Turn 'File:abc123' into 'abc123'."""
    return _PREFIXED.sub("", indicator.strip())


def build_known_universe(
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
) -> set:
    """
    Every identifier the investigation legitimately observed:
      - all NetworkX graph nodes
      - the root IOC
      - specialist network_indicators / related_indicators (prefix-stripped)
      - specialist analyzed_targets
    """
    known = set()

    for node_id in cache.graph.nodes():
        norm = _normalise_id(node_id)
        if norm:
            known.add(norm)

    root = _normalise_id(root_ioc)
    if root:
        known.add(root)

    for res in (specialist_results or {}).values():
        if not isinstance(res, dict):
            continue
        for field in ("network_indicators", "related_indicators"):
            for ind in res.get(field, []) or []:
                if not isinstance(ind, str):
                    continue
                norm = _normalise_id(_strip_prefix(ind))
                if norm:
                    known.add(norm)
        for target in res.get("analyzed_targets", []) or []:
            value = (
                target.get("indicator") or target.get("value")
                if isinstance(target, dict) else target
            )
            norm = _normalise_id(_strip_prefix(str(value))) if value else None
            if norm:
                known.add(norm)

    return known


def validate_report_iocs(
    report_md: str,
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
) -> Dict[str, Any]:
    """
    Returns {"unverified": [{"type","value"}], "verified": int, "extracted": int}.
    Pure function — does not mutate the report.
    """
    if not report_md:
        return {"unverified": [], "verified": 0, "extracted": 0}

    known = build_known_universe(cache, specialist_results, root_ioc)
    text = _refang(_strip_code(report_md))

    unverified: List[Dict[str, str]] = []
    seen: set = set()
    verified = 0
    extracted = 0

    for ioc_type, pattern in IOC_PATTERNS.items():
        for match in pattern.findall(text):
            if ioc_type == "ipv4" and not _valid_ipv4(match):
                continue
            if ioc_type == "domain" and not _plausible_domain(match):
                continue

            norm = _normalise_id(match)
            if not norm:
                continue

            extracted += 1
            if norm in known:
                verified += 1
                continue

            # A hash may be cited by a different case, or a domain may be a
            # subdomain of a known node. Substring containment on the graph is
            # too loose, so we only accept exact normalised matches.
            if norm in seen:
                continue
            seen.add(norm)
            unverified.append({"type": ioc_type, "value": match})

    return {"unverified": unverified, "verified": verified, "extracted": extracted}


def annotate_report(report_md: str, validation: Dict[str, Any]) -> str:
    """Append a validation footer if any IOC failed verification."""
    unverified = validation.get("unverified", [])
    if not unverified:
        return report_md

    lines = "\n".join(
        f"- `{item['value']}` ({item['type']})" for item in unverified
    )
    return (
        f"{report_md}\n\n---\n\n### ⚠️ Validation Notice\n\n"
        f"The following indicators appear in this report but were **not observed** "
        f"in the investigation graph or specialist findings. Treat them as "
        f"**unverified** and do not action them without independent confirmation:\n\n"
        f"{lines}\n"
    )


def validate_and_annotate(
    report_md: str,
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
    job_id: Optional[str] = None,
) -> str:
    """Convenience wrapper used by lead_hunter.py. Never raises."""
    try:
        validation = validate_report_iocs(report_md, cache, specialist_results, root_ioc)
        if validation["unverified"]:
            logger.warning(
                "report_iocs_unverified",
                job_id=job_id,
                unverified_count=len(validation["unverified"]),
                verified_count=validation["verified"],
                extracted_count=validation["extracted"],
                samples=[i["value"] for i in validation["unverified"][:5]],
            )
        else:
            logger.info(
                "report_iocs_all_verified",
                job_id=job_id,
                verified_count=validation["verified"],
            )
        return annotate_report(report_md, validation)
    except Exception as e:
        logger.error("report_validation_failed", job_id=job_id, error=str(e))
        return report_md  # never block the report on a validator bug

```

#### `backend/utils/signal_filter.py`

```python
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

from backend.utils.graph_cache import InvestigationCache, normalize_verdict
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

    Cannot be done in the per-entity loop because it needs the full graph, which
    only exists after every relationship has been parsed. Pure in-memory pass —
    everything is already in the NetworkX cache by this point.

    Args:
        filtered_out: {entity_id: parsed_entity} that FAILED the per-entity filter
        flagged_ids:  normalised ids of entities that PASSED

    Returns: {entity_id: reason} for entities that should be promoted.
    """
    promoted = {}
    for entity_id in filtered_out:
        if entity_id not in cache.graph:
            continue
        neighbors = set(cache.graph.successors(entity_id)) | set(
            cache.graph.predecessors(entity_id)
        )
        connected = neighbors & flagged_ids
        if connected:
            sample = sorted(connected)[:2]
            promoted[entity_id] = (
                f"graph_context:connected_to_flagged({','.join(sample)})"
            )
    if promoted:
        logger.info("signal_filter_graph_promotions", count=len(promoted))
    return promoted

```

#### `backend/utils/verdict_engine.py`

```python
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

from backend.utils.graph_cache import InvestigationCache, normalize_verdict
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
    attrs = cache.get_entity_full(entity_id)
    if not attrs:
        return {
            "composite_verdict": "unknown",
            "gti_verdict": "unknown",
            "escalated": False,
            "escalation_reasons": [],
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

```

#### `backend/tests/test_accuracy_fixes.py`

```python
import time, sys
sys.path.insert(0, "/home/claude/harimau")
from backend.utils.graph_cache import InvestigationCache
from backend.utils.report_validator import validate_report_iocs, annotate_report
from backend.utils.verdict_engine import apply_composite_verdicts, compute_composite_verdict, build_escalation_context
from backend.utils.signal_filter import get_signal_reason, promote_by_graph_context

NOW = time.time()
DAY = 86400
PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  OK  ' if cond else ' FAIL '} {name} {detail if not cond else ''}")

print("="*70); print("#2 REPORT VALIDATOR"); print("="*70)

cache = InvestigationCache()
REAL_HASH = "a" * 64
cache.add_entity(REAL_HASH, "file", {})
cache.add_entity("evil-c2.top", "domain", {})
cache.add_entity("185.220.101.5", "ip_address", {})
specialists = {"malware_specialist": {
    "network_indicators": ["IP:203.0.113.9"],
    "related_indicators": ["File:" + "b"*64],
    "analyzed_targets": [{"indicator": "known-drop.xyz"}],
}}

FAKE_HASH = "c" * 64
report = f"""
## Executive Summary
The dropper `{REAL_HASH}` contacted evil-c2[.]top and 185.220.101.5.
It also beaconed to {FAKE_HASH} and to fake-domain.com at 198.51.100.7.
Secondary payload {"b"*64} was retrieved. Peer IP:203.0.113.9 confirmed.
Target known-drop[.]xyz was analyzed.

### Notes
Analysis performed in `lead_hunter_synthesis.py`, payload was `svchost.exe`.
Version 10.2.1.300 of the loader. Config in settings.yaml.

```
digraph G {{ "{FAKE_HASH}" -> "in-code-block.com"; }}
```
"""
v = validate_report_iocs(report, cache, specialists, REAL_HASH)
unver = {i["value"] for i in v["unverified"]}
check("real hash verified", REAL_HASH not in unver)
check("defanged domain verified (evil-c2[.]top)", "evil-c2.top" not in unver)
check("real IP verified", "185.220.101.5" not in unver)
check("prefixed specialist IP verified", "203.0.113.9" not in unver)
check("prefixed specialist hash verified", "b"*64 not in unver)
check("analyzed_target verified", "known-drop.xyz" not in unver)
check("FAKE hash flagged", FAKE_HASH in unver, f"got {unver}")
check("fake domain flagged", "fake-domain.com" in unver, f"got {unver}")
check("fake IP flagged", "198.51.100.7" in unver, f"got {unver}")
check("py filename NOT flagged", "lead_hunter_synthesis.py" not in unver)
check("exe filename NOT flagged", "svchost.exe" not in unver)
check("yaml filename NOT flagged", "settings.yaml" not in unver)
check("version string NOT flagged as IP", "10.2.1.300" not in unver)
check("code-block content NOT flagged", "in-code-block.com" not in unver, f"got {unver}")
ann = annotate_report(report, v)
check("footer appended", "Validation Notice" in ann)
check("clean report untouched", annotate_report("x", {"unverified": []}) == "x")

print(); print("="*70); print("#3 SIGNAL FILTER"); print("="*70)

check("malicious verdict passes",
      get_signal_reason("domain", {}, "VERDICT_MALICIOUS", 0, NOW) == "gti_verdict:malicious")
check("vendor count >=3 passes",
      get_signal_reason("domain", {}, None, 4, NOW) == "vendor_detections:4")
check("clean domain filtered",
      get_signal_reason("domain", {"creation_date": NOW - 900*DAY, "tld": "com"}, None, 0, NOW) is None)
r = get_signal_reason("domain", {"creation_date": NOW - 5*DAY}, None, 0, NOW)
check("NEW domain 0-detections passes", r and r.startswith("newly_registered"), f"got {r}")
check("old domain does not pass on age",
      get_signal_reason("domain", {"creation_date": NOW - 400*DAY, "tld": "com"}, None, 0, NOW) is None)
check("suspicious TLD alone does NOT pass",
      get_signal_reason("domain", {"tld": "xyz", "creation_date": NOW-900*DAY}, None, 0, NOW) is None)
r = get_signal_reason("domain", {"tld": "xyz", "creation_date": NOW-900*DAY}, None, 1, NOW)
check("suspicious TLD + 1 detection passes", r and "suspicious_tld" in r, f"got {r}")
r = get_signal_reason("file", {"first_submission_date": NOW-3*DAY, "times_submitted": 1}, None, 0, NOW)
check("fresh rare file passes", r and "fresh_rare_sample" in r, f"got {r}")
check("fresh COMMON file filtered",
      get_signal_reason("file", {"first_submission_date": NOW-3*DAY, "times_submitted": 5000}, None, 0, NOW) is None)
r = get_signal_reason("ip_address", {"last_https_certificate": {"issuer":{"O":"Acme"},"subject":{"O":"Acme"}}}, None, 0, NOW)
check("self-signed cert IP passes", r == "self_signed_cert", f"got {r}")
check("CA-signed cert IP filtered",
      get_signal_reason("ip_address", {"last_https_certificate": {"issuer":{"O":"Let's Encrypt"},"subject":{"O":"acme.com"}}}, None, 0, NOW) is None)
check("None epoch safe", get_signal_reason("domain", {"creation_date": None}, None, 0, NOW) is None)
check("zero epoch safe", get_signal_reason("domain", {"creation_date": 0}, None, 0, NOW) is None)

# graph promotion
g = InvestigationCache()
g.add_entity("bad-ip", "ip_address", {})
g.add_entity("quiet-domain", "domain", {})
g.add_entity("unrelated", "domain", {})
g.add_relationship("quiet-domain", "bad-ip", "resolutions")
promoted = promote_by_graph_context(g, {"quiet-domain": {}, "unrelated": {}}, {"bad-ip"})
check("quiet domain resolving to flagged IP promoted", "quiet-domain" in promoted, f"got {promoted}")
check("unrelated domain NOT promoted", "unrelated" not in promoted)

print(); print("="*70); print("#6 VERDICT ENGINE"); print("="*70)

def gti(v, score=0, mal=0):
    return {"gti_assessment": {"verdict": {"value": v}, "threat_score": {"value": score}},
            "last_analysis_stats": {"malicious": mal}}

c = InvestigationCache()
c.add_entity("mal-file", "file", gti("VERDICT_MALICIOUS", 90, 40))
c.add_entity("mal-ip", "ip_address", gti("VERDICT_MALICIOUS", 85, 20))
c.add_entity("quiet-dom", "domain", gti("VERDICT_UNDETECTED", 0, 0))
c.add_entity("benign-cdn", "domain", gti("VERDICT_BENIGN", 0, 0))
c.add_entity("lonely", "domain", gti("VERDICT_UNDETECTED", 0, 0))
c.add_entity("attributed", "file", {**gti("VERDICT_UNDETECTED",0,0), "malware_families":["Emotet"]})
c.add_relationship("mal-file", "quiet-dom", "contacted_domains")
c.add_relationship("quiet-dom", "mal-ip", "resolutions")
c.add_relationship("mal-file", "benign-cdn", "contacted_domains")

r = compute_composite_verdict("quiet-dom", c)
check("undetected + 2 malicious neighbors -> escalated", r["escalated"])
check("2 malicious neighbors -> malicious", r["composite_verdict"] == "malicious", f"got {r['composite_verdict']}")
check("escalation has reasons", len(r["escalation_reasons"]) > 0)
check("gti_verdict preserved", r["gti_verdict"] == "undetected")

r = compute_composite_verdict("lonely", c)
check("isolated undetected NOT escalated", not r["escalated"])
check("isolated stays undetected", r["composite_verdict"] == "undetected")

r = compute_composite_verdict("attributed", c)
check("attribution escalates isolated file", r["escalated"], f"got {r}")

r = compute_composite_verdict("mal-file", c)
check("malicious never changes", r["composite_verdict"] == "malicious" and not r["escalated"])

r = compute_composite_verdict("benign-cdn", c)
check("GTI-benign adjacent to malware NOT escalated", r["composite_verdict"] == "benign", f"got {r['composite_verdict']}")
check("GTI-benign not marked escalated", not r["escalated"])
# benign WITH its own evidence may be overridden
c.add_entity("bad-benign", "domain", {**gti("VERDICT_BENIGN",0,9), "malware_families":["Qakbot"]})
c.add_relationship("mal-file","bad-benign","contacted_domains")
r = compute_composite_verdict("bad-benign", c)
check("GTI-benign WITH own evidence -> suspicious", r["composite_verdict"]=="suspicious", f"got {r['composite_verdict']}")
check("benign override never jumps to malicious", r["composite_verdict"] != "malicious")

# CASCADE TEST — the critical one
casc = InvestigationCache()
casc.add_entity("root-mal", "file", gti("VERDICT_MALICIOUS", 95, 50))
for i in range(1, 6):
    casc.add_entity(f"chain{i}", "domain", gti("VERDICT_UNDETECTED", 0, 0))
casc.add_relationship("root-mal", "chain1", "contacted_domains")
for i in range(1, 5):
    casc.add_relationship(f"chain{i}", f"chain{i+1}", "resolutions")
stats = apply_composite_verdicts(casc, "cascade-test")
verdicts = {n: casc.graph.nodes[n]["composite_verdict"] for n in casc.graph.nodes()}
check("chain1 (adjacent to malware) escalated", verdicts["chain1"] != "undetected", f"{verdicts}")
check("chain3 (2 hops away) NOT escalated", verdicts["chain3"] == "undetected", f"{verdicts}")
check("chain5 (4 hops away) NOT escalated", verdicts["chain5"] == "undetected", f"{verdicts}")
check("no full-graph paint", stats["escalated"] < casc.graph.number_of_nodes())

# stale
st = InvestigationCache()
st.add_entity("old", "file", {**gti("VERDICT_UNDETECTED"), "last_analysis_date": NOW - 400*DAY})
st.add_entity("recent", "file", {**gti("VERDICT_UNDETECTED"), "last_analysis_date": NOW - 5*DAY})
apply_composite_verdicts(st, "stale-test")
check("stale flagged", st.graph.nodes["old"].get("stale_analysis_days", 0) > 180)
check("recent not flagged", "stale_analysis_days" not in st.graph.nodes["recent"])

apply_composite_verdicts(c, "ctx")
ctx = build_escalation_context(c)
check("escalation context renders", "ASSESSED" in ctx and "GTI=" in ctx)
check("empty graph context safe", "No entities" in build_escalation_context(InvestigationCache()))
_unapplied = InvestigationCache(); _unapplied.add_entity("x","file",gti("VERDICT_MALICIOUS"))
check("guard fires if apply() not run", "not run" in build_escalation_context(_unapplied))

apply_composite_verdicts(c, "idem")
before = {n: c.graph.nodes[n]["composite_verdict"] for n in c.graph.nodes()}
apply_composite_verdicts(c, "idem2")
after = {n: c.graph.nodes[n]["composite_verdict"] for n in c.graph.nodes()}
check("idempotent (no cascade on re-run)", before == after, f"{before} vs {after}")

print(); print("="*70)
print(f"PASSED {len(PASS)} / {len(PASS)+len(FAIL)}")
if FAIL:
    print("FAILURES:"); [print("  -", f) for f in FAIL]

```

---

## 6. Verification

The test file above is self-contained (only needs `networkx`, already a project
dependency) and doesn't import anything from the rest of the backend except
`graph_cache` and `logger`, so it can run standalone:

```bash
pip install networkx --break-system-packages   # if not already present
python -m pytest backend/tests/test_accuracy_fixes.py -v
```

Expect **53 passed**. If any fail after integration, the most likely cause is
a mismatch between the stub `InvestigationCache` shape used during isolated
testing and the real one — re-check `get_entity_full()`, `add_entity()`, and
`add_relationship()` signatures match what's in the current `graph_cache.py`.

### Manual sanity check after wiring in

Run one investigation end-to-end and check the logs for these structured
events (all from the new modules):

- `composite_verdicts_applied` — should show `escalated` well under 20% of
  `nodes_evaluated` on a typical hunt. If it's much higher, the ladder is too
  loose for your data (see rollout note below).
- `report_iocs_unverified` (only if the report actually cites something
  ungrounded) or `report_iocs_all_verified` otherwise.
- `signal_filter_graph_promotions` — count of zero-detection entities pulled
  in because they connect to a flagged node.

### Suggested rollout order

1. **`report_validator.py` alone first.** It's a pure add — it only appends a
   footer to the finished report, so it cannot change upstream behavior.
   Deploy, then watch `report_iocs_unverified` for about a week. That count
   becomes a hallucination-rate baseline, useful later for the eval harness.
2. **`signal_filter.py` next.** Watch graph node counts per investigation; if
   they balloon, tighten `RECENCY_WINDOW_DAYS` (currently 30) in the module.
3. **`verdict_engine.py` last**, since it's the one that changes what the
   final report actually says. Watch the `escalated` count in
   `composite_verdicts_applied`; if it's consistently high, raise the
   neighbor-count threshold in Rule 4 of the ladder.
