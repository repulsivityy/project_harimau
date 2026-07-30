import json
from typing import Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.utils.logger import get_logger
from backend.graph.state import AgentState
from backend.utils.graph_cache import InvestigationCache, normalize_verdict
from backend.utils.verdict_engine import build_escalation_context
from backend.utils.signal_filter import build_promotion_context
from backend.utils.dot_builder import (
    build_dot_skeleton,
    extract_dot_block,
    replace_dot_block,
    validate_dot,
)

logger = get_logger("agent_lead_hunter_synthesis")

HIGH_SIGNAL_THREAT_SCORE = 60
# Upper bound on how many edges feed the attack-flow diagram (and its prose
# mirror, the edge-tuple context block). Single cap shared by both consumers
# via _select_diagram_edges so they can never disagree on which edges made
# the cut.
DIAGRAM_EDGE_LIMIT = 40
IMPORTANT_RELATIONSHIPS = {
    "contacted_domains",
    "contacted_ips",
    "contacted_urls",
    "dropped_files",
    "embedded_domains",
    "embedded_ips",
    "embedded_urls",
    "communicating_files",
    "downloaded_files",
    "resolutions",
    "network_location",
    "subdomains",
}
MALWARE_TYPES = {"file"}
INFRA_TYPES = {"domain", "ip_address", "url"}


def _sanitise_label(label: Any) -> str:
    """
    Make an entity's display label safe to interpolate into a prompt context
    line.

    Labels are attacker-chosen: they come from `meaningful_name`, `names[0]`,
    `last_final_url` and `host_name`, i.e. the filename the malware author
    picked. The graph summary and the edge fact table render one line per
    entity/edge, so a label containing a newline would render as an extra,
    fully-formed line — letting a sample name fabricate a graph fact (a
    high-signal edge between entities that don't exist) in the LLM's context.
    Quotes are escaped for the same reason: they delimit the label field.
    """
    text = str(label)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    # Collapse anything that could start a new line or field in the rendering.
    for ch in ("\r\n", "\r", "\n", "\t"):
        text = text.replace(ch, " ")
    return text.strip()


def _node_label(node_id: str, data: dict) -> str:
    """Human-readable label for a graph node. Used in graph summary and edge tuples."""
    entity_type = data.get("entity_type", "unknown")
    if entity_type == "file":
        return data.get("meaningful_name") or (data.get("names") or [node_id])[0]
    if entity_type == "url":
        return data.get("last_final_url") or data.get("url") or node_id
    if entity_type == "domain":
        return data.get("host_name") or node_id
    return data.get("name") or data.get("title") or node_id


# --- PROMPT: FINAL SYNTHESIS ---
LEAD_HUNTER_SYNTHESIS_PROMPT = """
You are the Lead Threat Hunter and Investigation Commander.

**Role:**
You are responsible for the final synthesis of the investigation. You have received detailed reports from your specialist agents (Malware Analysis and Infrastructure Hunting).
Your job is to connect the dots, identify the broader campaign context, and write a cohesive final intelligence report.

**Inputs:**
1.  **Triage Context:** Initial assessment and key findings.
2.  **Specialist Reports:** Detailed analysis of files and infrastructure.
3.  **Investigation Graph:** The network of connections found.

**Verdict Handling:**
Some entities in the Investigation Graph carry an assessed verdict that differs from their raw GTI baseline verdict — this happens when graph context (e.g. adjacency to a confirmed-malicious entity) or corroborating evidence justified an escalation. When an entity's assessed verdict differs from its GTI baseline, state BOTH explicitly rather than presenting the escalation as if it were GTI's own finding (e.g. "GTI: undetected — assessed SUSPICIOUS because it resolves to a confirmed C2 IP"). Draw escalation reasons from the Verdict Escalations context block provided below; do not invent reasons that aren't listed there. If an entity's `stale_analysis_days` is present, note that its verdict may be outdated. This is additive context for narrating the investigation accurately — it does not change how threat scores are reported; threat scores are passed through from GTI as-is and should never be derived or adjusted. In the graph context below, `threat_score=unknown` means GTI returned no score for that entity at all — typically because it was discovered as a relationship descriptor rather than fetched directly — and must NOT be read as a low or benign score, nor substituted with a guess.

**Goal:**
Produce a comprehensive Markdown report that reads like a high-level Threat Intelligence product (e.g., similar to Mandiant or Red Canary reporting).

**Report Structure:** (Use strict Markdown)

## [Investigation Title: e.g., "Deep Dive into Emotet Campaign 2024"]

### Lead Threat Hunter - Investigation Synthesis

### 1. Executive Summary
High-level overview in 3-4 sentences: What threat infrastructure was discovered, malware capabilities identified, and key findings.

### 2. Attack Narrative:
Provide the attack narrative in 6-8 sentences: How does the attack chain work? Connect the malware behavior to the infrastructure. 
Explain the complete kill chain from delivery through post-exploitation. 

### 3. Investigation Timeline (Bullet Points)
*   Reconstruct the sequence of events based on timestamps and logical flow (e.g., Domain Registered -> Payload Hosted -> User Click -> C2 Callback).

### 4. Technical Analysis

#### 4.1 Threat Profile
**Threat Level**: [Critical/High/Medium/Low] - based on sophistication and reach
**Confidence**: [High/Medium/Low] - based on available evidence from GTI
**Attribution**: [Specific threat actor/APT group/Cybercrime group/Unknown]
**Campaign Type**: [Targeted espionage/Mass exploitation/Ransomware/Data theft/Botnet]
**Sophistication**: [Advanced/Moderate/Low] - based on TTPs and evasion techniques
**Assessment Justification**: Brief explanation of the profiling.

#### 4.2. Malware Profile
NOTE: Integrate findings from Malware Specialist
**Family/Verdict**: [e.g., Emotet / Malicious]
**Capabilities**: Summarize key capabilities (e.g., "Screenshots", "Keylogging", "Credential Theft", "Ransomware", "Data Exfiltration").
**Sophistication**: [Advanced/Moderate/Low] - based on TTPs and evasion techniques
**Relationships**: Did the malware drop any files (eg, a ransom note?)? Did it use a malicious driver or DLL? Was a living-off-the-land binary used?  
**Assessment Justification**: Brief explanation of the profiling.

#### 4.3. Infrastructure Mapping    
NOTE: Integrate findings from Infrastructure Specialist
Map the threat infrastructure and identify patterns:
- **DNS Infrastructure**: Shared nameservers, registrars, or domain patterns (e.g., "All C2 domains use Cloudflare NS")
- **Hosting Infrastructure**: Shared ASNs, IP ranges, or hosting providers (e.g., "15 domains resolve to same /24 subnet")
- **Relationships**: How are the domains/IPs connected? (e.g., "Domain A and B both dropped File C")

### 5. Attack Flow Diagram
You have been given an **Attack Flow Diagram Skeleton** in the context below — a complete, valid `digraph AttackChain { ... }` built directly from the investigation graph. Your job is to **annotate that skeleton**, not design a diagram from scratch.

**CRITICAL Graphviz Rules:**
- Reproduce the skeleton's structure verbatim: every node and every edge it contains must appear in your output, with the exact same node ids and the exact same edges. Do NOT add, remove, or rename any node or edge.
- Node ids in the skeleton are already the full, untruncated IOC (sha256, IP Address, URL, Domain) — never shorten, truncate, or re-label them.
- Permitted changes ONLY:
    - Styling attributes (colors, shapes, fonts, penwidth, etc.) to improve readability.
    - Grouping nodes into `subgraph cluster_*` blocks to convey attack phases (e.g. delivery, execution, C2, objectives).
    - Refining edge `label=` text to name the relationship more precisely (e.g. `resolves_to` -> "Resolves To C2").
- Wrap the output in a ```dot ... ``` block.
- Use quotes for any label with spaces.
- **Layout Optimization:**
    - Use `rankdir=TB` (top to bottom) for a clearer, vertical flow.
    - Set `graph [splines=ortho];` for cleaner lines if many connections exist.
    - If the graph is too wide, use `unflatten` logic (grouping nodes) or suggest multiple connected subgraphs.

### 6. Intelligence Gaps & Pivots
*   Identify what is still unknown.
*   Suggest future hunting pivots (e.g., "Monitor ASN 12345 for new domains").

### 7. Attribution and Context
**Attribution Indicators**:
*   Mention any overlaps with known threat actors or campaigns.
*   Cite specific TTPs or infrastructure patterns that match known groups.

### 8. Final Assessment
Provide a final assessment of the investigation including any recommendations.

### 9. Additional Notes
*   Include any additional relevant information or insights.
*   Include 3-5 hunt hypotheses to hunt for the same threat actor in the future.

### 10. Appendix
*   Include all IOCs in a JSON array wrapped inside an `iocs` code block. Do NOT use a Markdown table.
*   Follow this exact format:
```iocs
[
  { "type": "Domain", "value": "example.com", "notes": "C2 Domain", "confidence": "Medium" },
  { "type": "IP Address", "value": "1.2.3.4", "notes": "Open Directory to drop files", "confidence": "Low" },
  { "type": "URL", "value": "https://example.com", "notes": "Phishing URL", "confidence": "High" },
  { "type": "File Hash", "value": "example.exe", "notes": "Ransomware", "confidence": "High" }
]
```

## Output Instructions:
- Return ONLY the Markdown text.
- Be professional, concise, and authoritative.
- Do NOT wrap the entire output in a JSON object. Return a standard Markdown document, except for the requested `iocs` JSON code block.
"""


def _build_triage_context(state: AgentState) -> str:
    """Build a concise triage context block for final synthesis."""
    triage_analysis = state.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
    summary = triage_analysis.get("executive_summary", "N/A")
    key_findings = triage_analysis.get("key_findings", [])
    threat_context = triage_analysis.get("threat_context", {})

    lines = [f"Executive Summary: {summary}"]

    if key_findings:
        lines.append("Key Findings:")
        lines.extend(f"- {finding}" for finding in key_findings[:10])

    if threat_context:
        lines.append(f"Threat Context: {json.dumps(threat_context)}")

    return "\n".join(lines)


def _build_specialist_context(state: AgentState) -> str:
    """Build full specialist context for final synthesis — report + key structured fields."""
    specialist_data = state.get("specialist_results", {})
    if not specialist_data:
        return "No specialist findings available."

    sections = []
    for agent, res in specialist_data.items():
        sections.append(f"--- {agent.upper()} ---")
        sections.append(f"Verdict: {res.get('verdict', 'Unknown')}")
        
        # If there's raw_text and no summary/report, it indicates a parse failure where raw text was recovered
        summary = res.get('summary', '')
        raw_text = res.get('raw_text', '')
        
        if not summary and raw_text:
            sections.append(f"Summary: [Recovered from raw LLM output]\n{raw_text[:1500]}")
        else:
            sections.append(f"Summary: {summary or 'No summary'}")

        # Include full markdown report — this is the specialist's complete analysis
        markdown_report = res.get("markdown_report")
        if markdown_report:
            sections.append("Full Report:")
            sections.append(markdown_report)

        # Structured JSON dump removed — the markdown report already contains
        # the full analysis and duplicating it wastes tokens.

    return "\n".join(sections)


def _compute_node_details(cache) -> dict:
    """
    Per-node score/verdict/type summary. Shared by _build_graph_summary (text
    rendering) and _score_edges (edge relevance) so both consumers see the
    same numbers instead of independently re-deriving them.
    """
    node_details = {}
    for node_id, data in cache.graph.nodes(data=True):
        entity_type = data.get("entity_type", "unknown")
        gti_assessment = data.get("gti_assessment") or {}
        verdict = gti_assessment.get("verdict") or {}
        threat_score = gti_assessment.get("threat_score") or {}
        last_analysis_stats = data.get("last_analysis_stats") or {}

        # Raw GTI verdict value, preserved as-is (e.g. "VERDICT_MALICIOUS") under
        # "gti_verdict" so the baseline is never lost. The composite verdict
        # engine (verdict_engine.py) may have escalated this node beyond its
        # GTI baseline using graph context; when present, prefer it for the
        # "verdict" field consumers actually act on. composite_verdict is
        # already a normalized lowercase token (e.g. "suspicious"), so when it
        # is absent we normalize the GTI fallback the same way — keeping
        # "verdict" in one consistent format for downstream consumers
        # (_score_edges' normalize_verdict() call, graph-summary text
        # rendering) instead of mixing raw and normalized shapes.
        gti_verdict_raw = verdict.get("value") if isinstance(verdict, dict) else None
        composite_verdict = data.get("composite_verdict")

        # "score" coerces a missing threat_score.value to 0 because it feeds
        # arithmetic comparisons (>= 80, > HIGH_SIGNAL_THREAT_SCORE) and
        # sorted(...) keys elsewhere — making it None would raise TypeError
        # there. That coercion is misleading for *rendering*, though: 0 reads
        # as "confirmed benign" when it may really mean "GTI never scored
        # this entity", which is the common case for pivot-discovered nodes
        # (extract_gti_summary's docstring in graph_cache.py notes
        # relationship-listing tools pass descriptors_only=True, so pivot
        # entities usually arrive with no gti_assessment at all). "score_known"
        # is the presentation-only sibling: True only when GTI actually
        # supplied a value, so callers that render text (graph summary, edge
        # fact table) can say "unknown" instead of a fabricated 0.
        # Coerce to a real number rather than only None-guarding: GTI has been
        # seen to return the score as a string ({"value": "85"}), which would
        # otherwise flow into _compute_high_signal's `>= 80` and into
        # sorted(key=(score, malicious_count)) and raise
        # TypeError: '>=' not supported between 'str' and 'int'.
        # (CHANGELOG 0.6.1 records the sibling {"value": None} crash.)
        raw_score = threat_score.get("value") if isinstance(threat_score, dict) else None
        try:
            score_value = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            logger.warning("threat_score_unparseable", node=node_id, raw=repr(raw_score))
            score_value = None
        # Render 92, not 92.0 — this value is shown to the LLM verbatim.
        if score_value is not None and score_value.is_integer():
            score_value = int(score_value)
        score_known = score_value is not None

        node_details[node_id] = {
            "id": node_id,
            "type": entity_type,
            "label": _node_label(node_id, data),
            "score": score_value if score_known else 0,
            "score_known": score_known,
            "verdict": composite_verdict if composite_verdict else normalize_verdict(gti_verdict_raw),
            "gti_verdict": gti_verdict_raw,
            "malicious_count": last_analysis_stats.get("malicious", 0) if isinstance(last_analysis_stats, dict) else 0,
            "raw_attributes": data,
        }
    return node_details


def _compute_high_signal(cache, node_details: dict):
    """
    Determine which nodes qualify as high-signal and the supporting sets
    (important-relationships-by-node, malware/infra bridges) needed to explain
    why. Returns (high_signal_node_ids, important_relationships_by_node, bridges_malware_infra).
    """
    important_relationships_by_node = {node_id: set() for node_id in node_details}
    bridges_malware_infra = set()

    for source, target, data in cache.graph.edges(data=True):
        rel = data.get("relationship", "related_to")
        if rel in IMPORTANT_RELATIONSHIPS:
            important_relationships_by_node.setdefault(source, set()).add(rel)
            important_relationships_by_node.setdefault(target, set()).add(rel)

        source_type = node_details.get(source, {}).get("type")
        target_type = node_details.get(target, {}).get("type")
        if (
            (source_type in MALWARE_TYPES and target_type in INFRA_TYPES) or
            (source_type in INFRA_TYPES and target_type in MALWARE_TYPES)
        ):
            bridges_malware_infra.add(source)
            bridges_malware_infra.add(target)

    high_signal_node_ids = set()
    for node_id, node in node_details.items():
        qualifiers = 0
        if node["malicious_count"] > 5:
            qualifiers += 1
        if len(important_relationships_by_node.get(node_id, set())) >= 2:
            qualifiers += 1
        if node_id in bridges_malware_infra:
            qualifiers += 1

        # S1-T2: Qualifier for specialist discovery
        if "malware_context" in node.get("raw_attributes", {}) or "infra_context" in node.get("raw_attributes", {}):
            qualifiers += 1

        qualifies = node["score"] >= 80 or (node["score"] > HIGH_SIGNAL_THREAT_SCORE and qualifiers >= 2)
        if qualifies:
            high_signal_node_ids.add(node_id)

    return high_signal_node_ids, important_relationships_by_node, bridges_malware_infra


def _score_edges(cache, node_details: dict, high_signal_node_ids: set, root_ioc: Optional[str]) -> list:
    """
    Score every edge in the investigation graph for relevance and sort it,
    so downstream consumers (graph-summary key edges, Graphviz edge grounding)
    can sort-then-cap instead of truncating in arbitrary NetworkX insertion
    order. Single source of truth for edge relevance — previously
    _build_graph_summary's key_edges and _build_edge_tuples computed
    overlapping-but-different relevance logic independently and drifted apart.

    Root-adjacent edges always sort first (they anchor the attack-flow
    diagram/narrative), then by descending relevance score.
    """
    scored = []
    for source, target, data in cache.graph.edges(data=True):
        rel = data.get("relationship", "related_to")
        source_node = node_details.get(source, {})
        target_node = node_details.get(target, {})

        target_verdict = normalize_verdict(target_node.get("verdict"))
        vendor_count = target_node.get("malicious_count", 0)
        has_threat_signal = target_verdict in {"malicious", "suspicious"} or vendor_count > 0

        qualifiers = 0
        if rel in IMPORTANT_RELATIONSHIPS:
            qualifiers += 1
        if target in high_signal_node_ids:
            qualifiers += 1
        source_type = source_node.get("type")
        target_type = target_node.get("type")
        if (
            (source_type in MALWARE_TYPES and target_type in INFRA_TYPES) or
            (source_type in INFRA_TYPES and target_type in MALWARE_TYPES)
        ):
            qualifiers += 1

        node_score = max(source_node.get("score") or 0, target_node.get("score") or 0)

        scored.append({
            "source": source,
            "target": target,
            "relationship": rel,
            "score": node_score + qualifiers * 10,
            "root_adjacent": bool(root_ioc) and root_ioc in (source, target),
            "qualifiers": qualifiers,
            "has_threat_signal": has_threat_signal,
            "target_verdict": target_node.get("verdict") or "unknown",
            "target_malicious_count": vendor_count,
            # S4-T5: carry the attribute set _build_edge_tuples needs to be a
            # complete fact table, rather than computing source_type/target_type
            # here and throwing them away as before.
            "source_type": source_type,
            "target_type": target_type,
            "source_verdict": source_node.get("verdict") or "unknown",
            "target_score": target_node.get("score", 0),
            "target_score_known": target_node.get("score_known", False),
            "source_score": source_node.get("score", 0),
            "source_score_known": source_node.get("score_known", False),
        })

    scored.sort(key=lambda e: (e["root_adjacent"], e["score"]), reverse=True)
    return scored


def _is_high_signal_edge(edge: dict) -> bool:
    """
    The predicate the (now-removed) "Key Edges" graph-summary block used to
    select edges worth naming explicitly. Kept as one function so the edge
    selection and the fact table's `high_signal` flag cannot drift apart.
    """
    return bool(edge.get("has_threat_signal")) and edge.get("qualifiers", 0) >= 1


def _select_diagram_edges(scored_edges: list, limit: int = DIAGRAM_EDGE_LIMIT) -> list:
    """
    Single source of truth for "which edges make it into the attack-flow
    diagram (and its prose fact table)". Dedups on (source, target,
    relationship) and caps at `limit`.

    High-signal edges get first claim on the budget. Without that reservation a
    plain relevance-ordered cut loses them entirely on real hunts, because
    _score_edges sorts `root_adjacent` ahead of everything and derives
    node_score from `max(source_score, target_score)` — so a malicious root
    hands its own high score to *all* of its edges, including edges to benign
    zero-detection CDN domains, and those outrank confirmed-malicious
    infrastructure several hops out. triage.py adds a root->entity edge for
    every entity returned across 13 PRIORITY_RELATIONSHIPS at limit=10, so a
    root with 40+ adjacent edges is the normal case, not an edge case.
    Measured on a root with 45 benign adjacent edges plus 6 confirmed-malicious
    distant ones: a plain cap surfaced 0 of the 6.

    Within each tier _score_edges' ordering is preserved, so the diagram still
    anchors on root-adjacent edges once the high-signal ones are in.
    """
    high_signal, remainder = [], []
    for edge in scored_edges:
        (high_signal if _is_high_signal_edge(edge) else remainder).append(edge)

    selected = []
    seen = set()
    for edge in high_signal + remainder:
        key = (edge["source"], edge["target"], edge["relationship"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(edge)
        if len(selected) >= limit:
            break
    return selected


def _build_graph_summary(
    state: AgentState,
    cache: Optional[InvestigationCache] = None,
    node_details: Optional[dict] = None,
    high_signal_node_ids: Optional[set] = None,
    scored_edges: Optional[list] = None,
) -> str:
    """
    Summarize the investigation graph into compact, high-signal text for synthesis.
    This gives the Lead Hunter actual graph context without dumping the full cache.

    `cache` is optional and defaults to rebuilding from `state["investigation_graph"]`
    for backward compatibility with any caller that doesn't have an already-built
    cache on hand. Prefer passing an in-memory cache (e.g. one composite verdicts
    were already applied to) so this doesn't rebuild from pre-mutation state.

    `node_details` / `high_signal_node_ids` / `scored_edges` are optional
    precomputed values. When the caller (generate_final_report_llm) has
    already run the _compute_node_details -> _compute_high_signal ->
    _score_edges chain once (e.g. to also build the Graphviz skeleton), it
    should pass those results in here instead of letting this function
    silently redo the work with its own (potentially drifting) copy. Falls
    back to computing them internally when not supplied.
    """
    if cache is None:
        graph_state = state.get("investigation_graph")
        if not graph_state:
            return "No investigation graph available."
        cache = InvestigationCache(graph_state)

    stats = cache.get_stats()
    root_ioc = state.get("ioc")

    if node_details is None:
        node_details = _compute_node_details(cache)

    # important_relationships_by_node / bridges_malware_infra are only needed
    # for this function's own high-signal-node narrative fields; they aren't
    # part of the shared precomputed-params contract, so they're always
    # (cheaply — a single edge pass) derived here. When high_signal_node_ids
    # IS supplied, it still wins over the freshly-derived set below so the
    # node membership stays consistent with whatever the caller shared with
    # the Graphviz skeleton.
    computed_high_signal_node_ids, important_relationships_by_node, bridges_malware_infra = (
        _compute_high_signal(cache, node_details)
    )
    if high_signal_node_ids is None:
        high_signal_node_ids = computed_high_signal_node_ids

    relationship_counts = {}
    for _source, _target, data in cache.graph.edges(data=True):
        rel = data.get("relationship", "related_to")
        relationship_counts[rel] = relationship_counts.get(rel, 0) + 1

    high_signal_nodes = [
        {
            **node_details[node_id],
            "important_relationships": sorted(important_relationships_by_node.get(node_id, set())),
            "bridges_malware_infra": node_id in bridges_malware_infra,
        }
        for node_id in node_details
        if node_id in high_signal_node_ids
    ]
    high_signal_nodes = sorted(
        high_signal_nodes,
        key=lambda n: (n["score"], n["malicious_count"]),
        reverse=True
    )[:15]

    if scored_edges is None:
        scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)

    root_neighbors = []
    if root_ioc and root_ioc in cache.graph:
        for neighbor in cache.graph.neighbors(root_ioc):
            rels = {
                edge_data.get("relationship", "related_to")
                for _, edge_data in cache.graph[root_ioc][neighbor].items()
            }
            root_neighbors.append(f"- {root_ioc} -> {neighbor} via {', '.join(sorted(rels))}")

    return (
        f"Graph Stats: nodes={stats['nodes']}, edges={stats['edges']}, "
        f"entity_types={json.dumps(stats['entity_types'])}\n"
        f"Relationship Counts: {json.dumps(relationship_counts)}\n"
        f"High-Signal Nodes:\n" +
        (
            "\n".join(
                f"- {n['type']}: {n['id']} | label={_sanitise_label(n['label'])} | "
                f"verdict={n['verdict'] or 'unknown'} | "
                f"threat_score={'unknown' if not n.get('score_known') else n['score']} | "
                f"malicious_vendors={n['malicious_count']} | "
                f"important_relationships={', '.join(n['important_relationships']) or 'none'} | "
                f"bridges_malware_infra={n['bridges_malware_infra']}"
                for n in high_signal_nodes
            )
            if high_signal_nodes else "- None"
        ) +
        "\nRoot IOC Relationships:\n" +
        ("\n".join(root_neighbors[:15]) if root_neighbors else "- None")
    )

def _build_edge_tuples(
    state: AgentState,
    cache: Optional[InvestigationCache] = None,
    node_details: Optional[dict] = None,
    high_signal_node_ids: Optional[set] = None,
    scored_edges: Optional[list] = None,
) -> str:
    """
    Generate the edge fact table used as narrative grounding for the Lead
    Hunter's prose (attack narrative, infrastructure mapping, relationship
    naming, etc.) — NOT the Graphviz diagram source; that's now
    generate_final_report_llm's build_dot_skeleton, built from the same edge
    selection so the two can't disagree.

    Keyed on real entity ids (matching the DOT skeleton's node ids — the
    previous label-keyed rendering here was the last remaining identifier
    inconsistency between the diagram and its prose mirror, since two
    distinct entities can share a display label). Each line carries the full
    attribute set _score_edges computes for both endpoints — entity type,
    verdict, threat score — plus the relationship name, the target's
    malicious-vendor count, and a high_signal flag preserving the same
    predicate the old (now-removed) "Key Edges" graph-summary section used
    (has_threat_signal and qualifiers >= 1), so that signal isn't lost by
    consolidating the two blocks into this one. threat_score renders as
    "unknown" rather than a misleading 0 when GTI supplied no score for that
    entity (see _compute_node_details' score_known). Where a node's display
    label differs from its id, the label is appended for that endpoint — file
    names carry real analyst signal — but the id stays the primary key.

    Edges are relevance-sorted (root-adjacent first, then by score, via
    _score_edges) before the shared _select_diagram_edges dedup+cap is
    applied, so the highest-signal and root-anchored edges always survive
    truncation instead of whatever NetworkX happened to iterate first.

    `cache` is optional and defaults to rebuilding from `state["investigation_graph"]`
    for backward compatibility with any caller that doesn't have an already-built
    cache on hand. Prefer passing an in-memory cache (e.g. one composite verdicts
    were already applied to) so this doesn't rebuild from pre-mutation state.

    `node_details` / `high_signal_node_ids` / `scored_edges` are optional
    precomputed values — see _build_graph_summary's docstring for why.
    """
    if cache is None:
        graph_state = state.get("investigation_graph")
        if not graph_state:
            return "No graph data available."
        cache = InvestigationCache(graph_state)

    root_ioc = state.get("ioc")

    if node_details is None:
        node_details = _compute_node_details(cache)
    if high_signal_node_ids is None:
        high_signal_node_ids, _important_rels, _bridges = _compute_high_signal(cache, node_details)
    if scored_edges is None:
        scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)

    diagram_edges = _select_diagram_edges(scored_edges)

    def _endpoint(entity_id: str) -> str:
        label = node_details.get(entity_id, {}).get("label")
        if label and label != entity_id:
            return f'{entity_id} label="{_sanitise_label(label)}"'
        return entity_id

    def _render_score(known: bool, value) -> str:
        return "unknown" if not known else value

    lines = []
    for edge in diagram_edges:
        high_signal = _is_high_signal_edge(edge)
        source_score = _render_score(edge.get("source_score_known", False), edge.get("source_score", 0))
        target_score = _render_score(edge.get("target_score_known", False), edge.get("target_score", 0))
        lines.append(
            f"- {_endpoint(edge['source'])} "
            f"({edge.get('source_type', 'unknown')}, verdict={edge.get('source_verdict', 'unknown')}, "
            f"threat_score={source_score}) "
            f"-[{edge['relationship']}]-> "
            f"{_endpoint(edge['target'])} "
            f"({edge.get('target_type', 'unknown')}, verdict={edge['target_verdict']}, "
            f"threat_score={target_score}, malicious_vendors={edge['target_malicious_count']}) "
            f"| high_signal={'yes' if high_signal else 'no'}"
        )

    return "\n".join(lines)


async def generate_final_report_llm(state: AgentState, llm, cache: Optional[InvestigationCache] = None) -> str:
    """
    Executes the final synthesis logic:
    1. Gathers context (Triage + Specialist Reports + Graph).
    2. Prompts the LLM to write the final markdown report.

    `cache` is optional. When the caller (lead_hunter.py's synthesis branch)
    already has an in-memory InvestigationCache with composite verdicts applied
    (see verdict_engine.apply_composite_verdicts), it should pass that cache
    directly here so escalations aren't lost by rebuilding from pre-mutation
    `state["investigation_graph"]`. Falls back to rebuilding from state only if
    no cache is supplied.
    """
    job_id = state.get("job_id")
    logger.info("lead_hunter_synthesis_start", job_id=job_id)

    cache = cache if cache is not None else InvestigationCache(state.get("investigation_graph"))

    # S1-T5: Error Recovery Guard
    specialist_data = state.get("specialist_results", {})
    if specialist_data and all(res.get("verdict") == "System Error" for res in specialist_data.values()):
        logger.error("lead_hunter_synthesis_aborted_all_specialists_failed", job_id=job_id)
        return """## ❌ Investigation Failed

The investigation was aborted because all specialist agents encountered critical system errors. 
Please review the system logs for stack traces.

### Error Details
No actionable intelligence could be synthesized. The original indicator may be malformed or external systems may be unreachable.
"""

    # Compute the _compute_node_details -> _compute_high_signal -> _score_edges
    # chain exactly once here, and share the results with _build_graph_summary,
    # _build_edge_tuples, and the Graphviz skeleton below. Previously each of
    # the first two recomputed this chain independently — harmless for the
    # text-only summary, but for the diagram it meant the skeleton and the
    # edge-tuple prose could drift apart. All three now see the same numbers.
    root_ioc = state.get("ioc")
    node_details = _compute_node_details(cache)
    high_signal_node_ids, _important_rels, _bridges = _compute_high_signal(cache, node_details)
    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)

    triage_context = _build_triage_context(state)
    specialist_context = _build_specialist_context(state)
    graph_summary = _build_graph_summary(
        state, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    edge_tuples = _build_edge_tuples(
        state, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    escalation_context = build_escalation_context(cache)
    promotion_context = build_promotion_context(cache)

    # Attack-flow diagram: the backend builds a deterministic, fully-grounded
    # skeleton (real graph entity ids, never display labels) from the same
    # edge selection as edge_tuples above, and the LLM is asked to annotate
    # it rather than invent a diagram from scratch. Whatever comes back is
    # validated against this exact node/edge set further down, with a
    # deterministic fallback to the skeleton itself if validation fails.
    diagram_edges = _select_diagram_edges(scored_edges)
    skeleton = build_dot_skeleton(node_details, diagram_edges, root_ioc)

    allowed_nodes = {edge["source"] for edge in diagram_edges} | {edge["target"] for edge in diagram_edges}
    if root_ioc and root_ioc in node_details:
        allowed_nodes.add(root_ioc)
    allowed_edges = {(edge["source"], edge["target"]) for edge in diagram_edges}

    # Format context
    context = f"""
    Use ALL input sections together when writing the final synthesis.

    **Triage Context:**
    {triage_context}

    **Specialist Summaries:**
    {specialist_context}

    **Investigation Graph Summary:**
    {graph_summary}

    **Attack Flow Diagram Skeleton (annotate this — do NOT add, remove, or rename any node or edge):**
    ```dot
    {skeleton}
    ```

    **Graph Edge Facts (high-signal edges first — use these to name relationships and entity types accurately; the diagram comes from the skeleton above):**
    {edge_tuples}

    **Verdict Escalations (graph-context analysis):**
    {escalation_context}

    **Graph-Context Promotions:**
    {promotion_context}
    """

    messages = [
        SystemMessage(content=LEAD_HUNTER_SYNTHESIS_PROMPT),
        HumanMessage(content=f"Please generate the final report based on:\n{context}")
    ]
    
    try:
        response = await llm.ainvoke(messages)
        logger.info("lead_hunter_synthesis_complete", job_id=job_id)

        # Some models (e.g. Gemini "thinking" preview models) return `.content`
        # as a list of content blocks (with thought-signature metadata) rather
        # than a plain string. A bare str() cast would stringify the whole
        # list/dict structure instead of the actual report text. Mirrors the
        # established extraction pattern used in triage.py / malware.py /
        # infrastructure.py's manual-fallback paths.
        raw_content = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw_content, list):
            raw_content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_content])
        elif not isinstance(raw_content, str):
            raw_content = str(raw_content)

        # Deterministic Graphviz fallback (S4-T3): validate whatever ```dot
        # block the LLM returned against the skeleton's own node/edge set.
        # This MUST happen here, before returning — lead_hunter.py runs
        # validate_and_annotate on the result next, and report_validator.py
        # strips DOT blocks before IOC extraction, so the fence must already
        # be final by the time this function returns. A bug in this step must
        # never lose an otherwise-successful report, hence the broad except.
        try:
            extracted_dot = extract_dot_block(raw_content)
            if extracted_dot is None:
                logger.warning(
                    "dot_validation_failed",
                    job_id=job_id,
                    reasons=["no ```dot fenced block found in LLM output"],
                )
                raw_content = replace_dot_block(raw_content, skeleton)
            else:
                # required_edges makes this a completeness check as well as a
                # soundness one: without it an empty `digraph AttackChain { }`
                # validates (it invents nothing) and the user gets a blank
                # diagram — the exact failure the skeleton exists to prevent.
                ok, reasons = validate_dot(
                    extracted_dot, allowed_nodes, allowed_edges,
                    required_edges=allowed_edges,
                )
                if ok:
                    logger.info("dot_validation_passed", job_id=job_id)
                else:
                    logger.warning("dot_validation_failed", job_id=job_id, reasons=reasons)
                    raw_content = replace_dot_block(raw_content, skeleton)
        except Exception as dot_error:
            logger.error("dot_validation_error", job_id=job_id, error=str(dot_error))
            # raw_content is returned unmodified — a validator bug must never
            # lose a successfully generated report.

        return raw_content
    except Exception as e:
        logger.error("lead_hunter_synthesis_error", job_id=job_id, error=str(e))
        return f"# Analysis Error\n\nFailed to generate final report. Error: {str(e)}"
