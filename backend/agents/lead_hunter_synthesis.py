import json
from langchain_core.messages import SystemMessage, HumanMessage
from backend.utils.logger import get_logger
from backend.graph.state import AgentState
from backend.utils.graph_cache import InvestigationCache

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
*   Include all IOCs in a table format 
| IOC Type | Value | Notes | Confidence |
| --- | --- | --- | --- |
| Domain | example.com | C2 Domain | Medium |
| IP Address | [IP_ADDRESS] | Open Directory to drop files | Low |
| URL | https://example.com | Phishing URL | High |
| File Hash | example.exe | Ransomware | High |

## Output Instructions:
- Return ONLY the Markdown text.
- Be professional, concise, and authoritative.
- Do NOT output JSON. Output pure Markdown.
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
    """Build a concise specialist-summary block for final synthesis."""
    specialist_data = state.get("specialist_results", {})
    if not specialist_data:
        return "No specialist findings available."

    sections = []
    for agent, res in specialist_data.items():
        sections.append(f"--- {agent.upper()} ---")
        sections.append(f"Verdict: {res.get('verdict', 'Unknown')}")
        sections.append(f"Summary: {res.get('summary', 'No summary')}")

        markdown_report = res.get("markdown_report")
        if markdown_report:
            sections.append("Report Excerpt:")
            sections.append(markdown_report[:2000])

        sections.append(f"Structured Findings: {json.dumps(res, indent=1)}")

    return "\n".join(sections)


def _build_graph_summary(state: AgentState) -> str:
    """
    Summarize the investigation graph into compact, high-signal text for synthesis.
    This gives the Lead Hunter actual graph context without dumping the full cache.
    """
    graph_state = state.get("investigation_graph")
    if not graph_state:
        return "No investigation graph available."

    cache = InvestigationCache(graph_state)
    stats = cache.get_stats()
    root_ioc = state.get("ioc")
    node_details = {}
    important_relationships_by_node = {}
    bridges_malware_infra = set()
    relationship_counts = {}

    def _node_label(node_id: str, data: dict) -> str:
        entity_type = data.get("entity_type", "unknown")
        if entity_type == "file":
            return data.get("meaningful_name") or (data.get("names") or [node_id])[0]
        if entity_type == "url":
            return data.get("last_final_url") or data.get("url") or node_id
        if entity_type == "domain":
            return data.get("host_name") or node_id
        return data.get("name") or data.get("title") or node_id

    for node_id, data in cache.graph.nodes(data=True):
        entity_type = data.get("entity_type", "unknown")
        gti_assessment = data.get("gti_assessment") or {}
        verdict = gti_assessment.get("verdict") or {}
        threat_score = gti_assessment.get("threat_score") or {}
        last_analysis_stats = data.get("last_analysis_stats") or {}

        node_details[node_id] = {
            "id": node_id,
            "type": entity_type,
            "label": _node_label(node_id, data),
            "score": threat_score.get("value", 0) if isinstance(threat_score, dict) else 0,
            "verdict": verdict.get("value") if isinstance(verdict, dict) else None,
            "malicious_count": last_analysis_stats.get("malicious", 0) if isinstance(last_analysis_stats, dict) else 0,
        }
        important_relationships_by_node[node_id] = set()

    for source, target, data in cache.graph.edges(data=True):
        rel = data.get("relationship", "related_to")
        relationship_counts[rel] = relationship_counts.get(rel, 0) + 1

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

    high_signal_nodes = []
    high_signal_node_ids = set()
    for node_id, node in node_details.items():
        if node["score"] <= HIGH_SIGNAL_THREAT_SCORE:
            continue

        qualifiers = 0
        if node["malicious_count"] > 5:
            qualifiers += 1
        if len(important_relationships_by_node.get(node_id, set())) >= 2:
            qualifiers += 1
        if node_id in bridges_malware_infra:
            qualifiers += 1

        if qualifiers >= 2:
            high_signal_nodes.append({
                **node,
                "important_relationships": sorted(important_relationships_by_node.get(node_id, set())),
                "bridges_malware_infra": node_id in bridges_malware_infra,
            })
            high_signal_node_ids.add(node_id)

    high_signal_nodes = sorted(
        high_signal_nodes,
        key=lambda n: (n["score"], n["malicious_count"]),
        reverse=True
    )[:15]

    key_edges = []
    for source, target, data in cache.graph.edges(data=True):
        rel = data.get("relationship", "related_to")
        target_node = node_details.get(target, {})
        source_node = node_details.get(source, {})

        verdict = (target_node.get("verdict") or "").lower()
        vendor_count = target_node.get("malicious_count", 0)
        has_threat_signal = verdict in {"malicious", "suspicious"} or vendor_count > 0
        if not has_threat_signal:
            continue

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

        if qualifiers >= 1:
            key_edges.append({
                "source": source,
                "target": target,
                "relationship": rel,
                "target_verdict": target_node.get("verdict") or "unknown",
                "target_malicious_count": vendor_count,
            })

    key_edges = key_edges[:25]

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

async def generate_final_report_llm(state: AgentState, llm) -> str:
    """
    Executes the final synthesis logic:
    1. Gathers context (Triage + Specialist Reports).
    2. Prompts the LLM to write the final markdown report.
    """
    triage_context = _build_triage_context(state)
    specialist_context = _build_specialist_context(state)
    graph_summary = _build_graph_summary(state)
    
    # Format context
    context = f"""
    Use ALL three input sections together when writing the final synthesis.
    
    **Triage Context:**
    {triage_context}

    **Specialist Summaries:**
    {specialist_context}

    **Investigation Graph Summary:**
    {graph_summary}
    """

    messages = [
        SystemMessage(content=LEAD_HUNTER_SYNTHESIS_PROMPT),
        HumanMessage(content=f"Please generate the final report based on:\n{context}")
    ]
    
    try:
        response = await llm.ainvoke(messages)
        
        # [CRITICAL FIX] ChatVertexAI sometimes returns a list of blocks instead of a string.
        # This breaks postgres `asyncpg` which expects a string for the final_report column.
        if isinstance(response.content, list):
            parts = []
            for block in response.content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, (dict, list)):
                        parts.append(json.dumps(text))
                    else:
                        parts.append(str(text))
                else:
                    parts.append(str(block))
            final_text = "".join(parts)
            return final_text
            
        return str(response.content)
    except Exception as e:
        logger.error("lead_hunter_synthesis_error", error=str(e))
        return f"# Analysis Error\n\nFailed to generate final report. Error: {str(e)}"
