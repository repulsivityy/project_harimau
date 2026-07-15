import json
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.utils.logger import get_logger
from backend.graph.state import AgentState
from backend.utils.graph_cache import InvestigationCache, normalize_verdict
from backend.utils.verdict_engine import build_escalation_context
from backend.utils.signal_filter import build_promotion_context

logger = get_logger("agent_lead_hunter_synthesis")

HIGH_SIGNAL_THREAT_SCORE = 60
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
Some entities in the Investigation Graph carry an assessed verdict that differs from their raw GTI baseline verdict — this happens when graph context (e.g. adjacency to a confirmed-malicious entity) or corroborating evidence justified an escalation. When an entity's assessed verdict differs from its GTI baseline, state BOTH explicitly rather than presenting the escalation as if it were GTI's own finding (e.g. "GTI: undetected — assessed SUSPICIOUS because it resolves to a confirmed C2 IP"). Draw escalation reasons from the Verdict Escalations context block provided below; do not invent reasons that aren't listed there. If an entity's `stale_analysis_days` is present, note that its verdict may be outdated. This is additive context for narrating the investigation accurately — it does not change how threat scores are reported; threat scores are passed through from GTI as-is and should never be derived or adjusted.

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
Create a Graphviz diagram showing the complete infrastructure and attack chain.
Where relevant, include the indicators that highlight that particular attack chain.

**CRITICAL Graphviz Rules:**
- Use DOT language syntax
- Wrap code in ```dot ... ``` block
- Use quotes for labels with spaces
- Show infrastructure relationships (domains -> IPs -> ASNs)
- Show attack progression (example: delivery -> execution -> C2 -> objectives)
- Show the full ioc (sha256, IP Address, URL, Domain), do not truncate them. 
- **Layout Optimization:**
    - Use `rankdir=TB` (top to bottom) for a clearer, vertical flow.
    - Set `graph [splines=ortho];` for cleaner lines if many connections exist.
    - If the graph is too wide, use `unflatten` logic (grouping nodes) or suggest multiple connected subgraphs.

**Example:**
```dot
digraph AttackChain {
  rankdir=TB;
  center=true;
  concentrate=true;
  bgcolor="ghostwhite"
  node [shape=box, style=filled, fillcolor=lightgray, fontname="Arial", fontsize=10];
  edge [fontname="Arial", fontsize=9];
  
  "Phishing Email" -> "malicious.doc" [label="Drops"];
  "malicious.doc" -> "C2 Domain" [label="Connects"];
  "C2 Domain" -> "IP: 1.2.3.4" [label="Resolves"];
}
```

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

        node_details[node_id] = {
            "id": node_id,
            "type": entity_type,
            "label": _node_label(node_id, data),
            "score": (threat_score.get("value") if isinstance(threat_score, dict) and threat_score.get("value") is not None else 0),
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
        })

    scored.sort(key=lambda e: (e["root_adjacent"], e["score"]), reverse=True)
    return scored


def _build_graph_summary(state: AgentState, cache: Optional[InvestigationCache] = None) -> str:
    """
    Summarize the investigation graph into compact, high-signal text for synthesis.
    This gives the Lead Hunter actual graph context without dumping the full cache.

    `cache` is optional and defaults to rebuilding from `state["investigation_graph"]`
    for backward compatibility with any caller that doesn't have an already-built
    cache on hand. Prefer passing an in-memory cache (e.g. one composite verdicts
    were already applied to) so this doesn't rebuild from pre-mutation state.
    """
    if cache is None:
        graph_state = state.get("investigation_graph")
        if not graph_state:
            return "No investigation graph available."
        cache = InvestigationCache(graph_state)

    stats = cache.get_stats()
    root_ioc = state.get("ioc")

    node_details = _compute_node_details(cache)
    high_signal_node_ids, important_relationships_by_node, bridges_malware_infra = (
        _compute_high_signal(cache, node_details)
    )

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

    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)
    key_edges = [e for e in scored_edges if e["has_threat_signal"] and e["qualifiers"] >= 1][:25]

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
                f"- {n['type']}: {n['id']} | label={n['label']} | "
                f"verdict={n['verdict'] or 'unknown'} | threat_score={n['score']} | "
                f"malicious_vendors={n['malicious_count']} | "
                f"important_relationships={', '.join(n['important_relationships']) or 'none'} | "
                f"bridges_malware_infra={n['bridges_malware_infra']}"
                for n in high_signal_nodes
            )
            if high_signal_nodes else "- None"
        ) +
        "\nRoot IOC Relationships:\n" +
        ("\n".join(root_neighbors[:15]) if root_neighbors else "- None") +
        "\nKey Edges:\n" +
        (
            "\n".join(
                f"- {edge['source']} -[{edge['relationship']}]-> {edge['target']} | "
                f"target_verdict={edge['target_verdict']} | "
                f"target_malicious_vendors={edge['target_malicious_count']}"
                for edge in key_edges
            )
            if key_edges else "- None"
        )
    )

def _build_edge_tuples(state: AgentState, cache: Optional[InvestigationCache] = None) -> str:
    """
    Generate a machine-readable edge list for grounding the Graphviz diagram.
    Each line is a DOT-compatible edge: "source_label" -> "target_label" [label="relationship"]
    The LLM can use these directly instead of reconstructing edges from prose.

    Edges are relevance-sorted (root-adjacent first, then by score, via
    _score_edges) before the cap is applied, so the highest-signal and
    root-anchored edges always survive truncation instead of whatever
    NetworkX happened to iterate first. Previously this took the first 40
    edges in raw insertion order, which could exhaust the cap on benign
    triage-phase noise before any specialist-discovered edge was considered.

    `cache` is optional and defaults to rebuilding from `state["investigation_graph"]`
    for backward compatibility with any caller that doesn't have an already-built
    cache on hand. Prefer passing an in-memory cache (e.g. one composite verdicts
    were already applied to) so this doesn't rebuild from pre-mutation state.
    """
    if cache is None:
        graph_state = state.get("investigation_graph")
        if not graph_state:
            return "No graph data available."
        cache = InvestigationCache(graph_state)

    root_ioc = state.get("ioc")

    node_details = _compute_node_details(cache)
    high_signal_node_ids, _important_rels, _bridges = _compute_high_signal(cache, node_details)
    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)

    lines = []
    seen = set()
    for edge in scored_edges:
        key = (edge["source"], edge["target"], edge["relationship"])
        if key in seen:
            continue
        seen.add(key)

        src_label = node_details.get(edge["source"], {}).get("label", edge["source"])
        tgt_label = node_details.get(edge["target"], {}).get("label", edge["target"])
        lines.append(f'  "{src_label}" -> "{tgt_label}" [label="{edge["relationship"]}"];')

    return "\n".join(lines[:40])  # Cap at 40 edges to limit token cost


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

    triage_context = _build_triage_context(state)
    specialist_context = _build_specialist_context(state)
    graph_summary = _build_graph_summary(state, cache)
    edge_tuples = _build_edge_tuples(state, cache)
    escalation_context = build_escalation_context(cache)
    promotion_context = build_promotion_context(cache)

    # Format context
    context = f"""
    Use ALL input sections together when writing the final synthesis.

    **Triage Context:**
    {triage_context}

    **Specialist Summaries:**
    {specialist_context}

    **Investigation Graph Summary:**
    {graph_summary}

    **Graph Edges (use these for your Graphviz diagram — do NOT invent edges):**
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
        return raw_content
    except Exception as e:
        logger.error("lead_hunter_synthesis_error", job_id=job_id, error=str(e))
        return f"# Analysis Error\n\nFailed to generate final report. Error: {str(e)}"
