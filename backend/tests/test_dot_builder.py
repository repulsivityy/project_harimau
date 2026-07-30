"""
Tests for S4-T3 (Deterministic Graphviz).

Background: the Lead Hunter's attack-flow diagram used to be authored
entirely freehand by the LLM, grounded only by a list of label-only DOT edge
lines that nothing validated. Two concrete bugs resulted: malformed DOT
silently renders a blank panel in the frontend's async d3-graphviz renderer,
and edges were keyed on *display labels* rather than real entity ids, so two
distinct entities could collapse into a single DOT node.

This suite covers backend.utils.dot_builder (skeleton construction, DOT
fence extraction/replacement, structural parsing, and validation) plus
backend.agents.lead_hunter_synthesis._select_diagram_edges (the single edge
selection shared by both the diagram and its prose mirror).

Plain pytest, no pytest-asyncio dependency — the one async test drives
generate_final_report_llm with asyncio.run and a stub LLM.
"""

import asyncio

from backend.utils.graph_cache import InvestigationCache
from backend.utils.dot_builder import (
    build_dot_skeleton,
    extract_dot_block,
    replace_dot_block,
    parse_dot_structure,
    validate_dot,
)
from backend.agents.lead_hunter_synthesis import (
    _compute_node_details,
    _compute_high_signal,
    _score_edges,
    _select_diagram_edges,
    generate_final_report_llm,
    DIAGRAM_EDGE_LIMIT,
)


class _StubLLM:
    """Minimal stand-in for the synthesis LLM. Records the messages it saw."""

    def __init__(self, body):
        self._body = body
        self.captured = None

    async def ainvoke(self, messages):
        self.captured = messages

        class _Response:
            content = self._body

        return _Response()


# ---------------------------------------------------------------------------
# Fixture: a small, realistic investigation graph — one file, two domains,
# one IP — populated the same way the specialists do
# (cache.add_entity(...) then cache.add_relationship(...)), with realistic
# gti_assessment shapes.
# ---------------------------------------------------------------------------

FILE_HASH = "a" * 64
DOMAIN_1 = "evil-c2.example.com"
DOMAIN_2 = "dropzone.example.net"
IP = "203.0.113.7"


def _build_cache() -> InvestigationCache:
    cache = InvestigationCache()
    cache.add_entity(FILE_HASH, "file", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 90}},
        "meaningful_name": "invoice_2024.exe",
    })
    cache.add_entity(DOMAIN_1, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_SUSPICIOUS"}, "threat_score": {"value": 65}},
    })
    cache.add_entity(DOMAIN_2, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_UNDETECTED"}, "threat_score": {"value": 5}},
    })
    cache.add_entity(IP, "ip_address", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 85}},
    })

    cache.add_relationship(FILE_HASH, DOMAIN_1, "contacted_domains")
    cache.add_relationship(FILE_HASH, DOMAIN_2, "embedded_domains")
    cache.add_relationship(DOMAIN_1, IP, "resolutions")
    cache.add_relationship(DOMAIN_2, IP, "resolutions")
    return cache


def _pipeline(cache: InvestigationCache, root_ioc: str = FILE_HASH):
    """Run the same node_details -> high_signal -> scored_edges -> diagram_edges
    -> skeleton chain generate_final_report_llm runs."""
    node_details = _compute_node_details(cache)
    high_signal_node_ids, _ir, _b = _compute_high_signal(cache, node_details)
    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)
    diagram_edges = _select_diagram_edges(scored_edges)
    skeleton = build_dot_skeleton(node_details, diagram_edges, root_ioc)
    return node_details, scored_edges, diagram_edges, skeleton


def _allowed_sets(node_details, diagram_edges, root_ioc):
    allowed_nodes = {e["source"] for e in diagram_edges} | {e["target"] for e in diagram_edges}
    if root_ioc and root_ioc in node_details:
        allowed_nodes.add(root_ioc)
    allowed_edges = {(e["source"], e["target"]) for e in diagram_edges}
    return allowed_nodes, allowed_edges


# ---------------------------------------------------------------------------
# build_dot_skeleton
# ---------------------------------------------------------------------------

def test_skeleton_keys_nodes_on_full_id_not_display_label():
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)

    # The full, untruncated 64-char hash must appear verbatim as a DOT node id.
    assert f'"{FILE_HASH}"' in skeleton

    parsed_nodes, _parsed_edges = parse_dot_structure(skeleton)
    expected_nodes = {FILE_HASH, DOMAIN_1, DOMAIN_2, IP}
    assert parsed_nodes == expected_nodes

    # The display label (meaningful_name) must NOT be used as the DOT node id
    # in its own right — only the real graph entity id may be.
    assert node_details[FILE_HASH]["label"] == "invoice_2024.exe"
    assert "invoice_2024.exe" not in parsed_nodes


def test_skeleton_contains_exactly_expected_edges_and_validates():
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)

    expected_edges = {(e["source"], e["target"]) for e in diagram_edges}
    assert expected_edges == {
        (FILE_HASH, DOMAIN_1),
        (FILE_HASH, DOMAIN_2),
        (DOMAIN_1, IP),
        (DOMAIN_2, IP),
    }

    _parsed_nodes, parsed_edges = parse_dot_structure(skeleton)
    assert parsed_edges == expected_edges

    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)
    ok, reasons = validate_dot(skeleton, allowed_nodes, allowed_edges)
    assert ok, reasons
    assert reasons == []


def test_skeleton_is_deterministic():
    skeleton_a = _pipeline(_build_cache())[3]
    skeleton_b = _pipeline(_build_cache())[3]
    assert skeleton_a == skeleton_b


def test_skeleton_root_ioc_included_even_without_edges():
    """A root IOC with no edges of its own must still get a node declaration."""
    cache = _build_cache()
    cache.add_entity("lonely-root.example.org", "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_UNDETECTED"}, "threat_score": {"value": 0}},
    })
    node_details = _compute_node_details(cache)
    high_signal_node_ids, _ir, _b = _compute_high_signal(cache, node_details)
    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, "lonely-root.example.org")
    diagram_edges = _select_diagram_edges(scored_edges)
    skeleton = build_dot_skeleton(node_details, diagram_edges, "lonely-root.example.org")

    assert '"lonely-root.example.org"' in skeleton
    assert "penwidth=3" in skeleton


def test_skeleton_escaping_survives_quotes_and_validates():
    """An entity id/label containing a literal double-quote must still
    produce syntactically valid, brace-balanced DOT that round-trips through
    validate_dot without being rejected."""
    node_details = {
        'node"a': {"id": 'node"a', "type": "domain", "label": 'node"a', "score": 10, "verdict": None},
        "node_b": {"id": "node_b", "type": "ip_address", "label": 'weird "label" value', "score": 90, "verdict": "malicious"},
    }
    diagram_edges = [{"source": 'node"a', "target": "node_b", "relationship": 'go "there" now'}]

    skeleton = build_dot_skeleton(node_details, diagram_edges, root_ioc=None)

    assert skeleton.count("{") == skeleton.count("}")

    allowed_nodes = {'node"a', "node_b"}
    allowed_edges = {('node"a', "node_b")}
    ok, reasons = validate_dot(skeleton, allowed_nodes, allowed_edges)
    assert ok, reasons


# ---------------------------------------------------------------------------
# validate_dot: rejection paths
# ---------------------------------------------------------------------------

def test_validate_dot_rejects_invented_node():
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    bad = skeleton.replace(f'"{DOMAIN_2}"', '"totally-invented.example.com"')
    ok, reasons = validate_dot(bad, allowed_nodes, allowed_edges)
    assert not ok
    assert any("totally-invented.example.com" in r for r in reasons)


def test_validate_dot_rejects_invented_edge():
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    # DOMAIN_1 -> DOMAIN_2 is a real allowed node pair but not a real edge.
    bad = skeleton.rstrip().rstrip("}") + f'\n  "{DOMAIN_1}" -> "{DOMAIN_2}" [label="fabricated"];\n}}\n'
    ok, reasons = validate_dot(bad, allowed_nodes, allowed_edges)
    assert not ok
    assert any("unknown edge" in r for r in reasons)


def test_validate_dot_rejects_unquoted_invented_node():
    """
    DOT allows unquoted identifiers ([A-Za-z_]\\w* and numerals), so a parser
    that only recognises quoted tokens can be bypassed entirely: the LLM adds
    `attacker_infra [shape=box];` with no quotes and validation waves it
    through, which defeats the whole point of grounding the diagram.
    """
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    bad = skeleton.rstrip().rstrip("}") + "\n  attacker_infra [shape=box];\n}\n"
    ok, reasons = validate_dot(bad, allowed_nodes, allowed_edges)
    assert not ok
    assert any("attacker_infra" in r for r in reasons)


def test_validate_dot_rejects_unquoted_invented_edge():
    """Same bypass, via an unquoted edge statement rather than a declaration."""
    cache = _build_cache()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    bad = skeleton.rstrip().rstrip("}") + f"\n  {FILE_HASH} -> attacker_c2;\n}}\n"
    ok, reasons = validate_dot(bad, allowed_nodes, allowed_edges)
    assert not ok
    assert any("attacker_c2" in r for r in reasons)


def test_parse_dot_structure_keeps_unquoted_hex_id_intact():
    """
    A bare hex id must tokenise as one unit. If the numeral branch of the id
    pattern wins, "44d88612..." splits into "44" + the remainder, and the
    reported reasons become nonsense even though the verdict is still a reject.
    """
    nodes, edges = parse_dot_structure(f"digraph G {{ {FILE_HASH} -> attacker_c2; }}")
    assert FILE_HASH in nodes
    assert (FILE_HASH, "attacker_c2") in edges


def test_validate_dot_rejects_unbalanced_braces():
    ok, reasons = validate_dot('digraph AttackChain { "a" -> "b";', {"a", "b"}, {("a", "b")})
    assert not ok
    assert any("brace" in r for r in reasons)


def test_validate_dot_rejects_missing_digraph_header():
    ok, reasons = validate_dot('graph G { "a" -> "b"; }', {"a", "b"}, {("a", "b")})
    assert not ok
    assert any("digraph" in r for r in reasons)


def test_validate_dot_accepts_legitimately_annotated_variant():
    """
    The acceptance path: the LLM keeps the same nodes/edges but restyles them,
    groups them into a subgraph cluster, rewords edge labels, and re-cases
    node ids. If this is rejected, every real report would silently fall back
    to the unannotated skeleton and the LLM's styling work would always be
    discarded.
    """
    cache = _build_cache()
    node_details, _scored, diagram_edges, _skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    annotated = f'''digraph AttackChain {{
  rankdir=TB;
  bgcolor="white";
  subgraph cluster_phase1 {{
    label="Delivery";
    "{FILE_HASH.upper()}" [shape=box, style=filled, fillcolor=red, label="FILE\\n{FILE_HASH}"];
    "{DOMAIN_1.upper()}" [shape=ellipse, style=filled, fillcolor=orange, label="DOMAIN\\n{DOMAIN_1}"];
  }}
  subgraph cluster_phase2 {{
    label="Command and Control";
    "{DOMAIN_2.upper()}" [shape=ellipse, style=filled, fillcolor=yellow, label="DOMAIN\\n{DOMAIN_2}"];
    "{IP.upper()}" [shape=box3d, style=filled, fillcolor=darkred, label="IP\\n{IP}"];
  }}
  "{FILE_HASH.upper()}" -> "{DOMAIN_1.upper()}" [label="Contacts C2 Domain"];
  "{FILE_HASH.upper()}" -> "{DOMAIN_2.upper()}" [label="Embeds Dropzone Domain"];
  "{DOMAIN_1.upper()}" -> "{IP.upper()}" [label="Resolves To"];
  "{DOMAIN_2.upper()}" -> "{IP.upper()}" [label="Resolves To"];
}}'''

    ok, reasons = validate_dot(annotated, allowed_nodes, allowed_edges)
    assert ok, reasons


def test_validate_dot_accepts_full_range_of_invited_annotations():
    """
    False rejection is as damaging as false acceptance: it silently discards
    the annotation on every report, visible only in a log line. This exercises
    the constructs the synthesis prompt actively invites — graph-level
    attributes outside any fixed allowlist (fontcolor, labelloc), comments,
    HTML-like labels, rank=same groups, edge chains, and multi-line attribute
    lists. An allowlist-based attribute stripper fails this.
    """
    cache = _build_cache()
    node_details, _scored, diagram_edges, _skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    annotated = f'''digraph AttackChain {{
  // Attack phases, top to bottom
  /* styling below is cosmetic only */
  rankdir=TB;
  fontcolor="darkslategray";
  labelloc="t";
  tooltip="Attack flow";
  graph [splines=ortho];
  node [shape=box, style=filled];

  "{FILE_HASH}" [
      shape=box,
      fillcolor=lightcoral,
      label=<<B>Dropper</B>>
  ];
  {{ rank=same; "{DOMAIN_1}"; "{DOMAIN_2}"; }}

  subgraph cluster_c2 {{
    label="Command and Control";
    "{IP}" [shape=box3d];
  }}

  "{FILE_HASH}" -> "{DOMAIN_1}" [label="Contacts -> beacons"];
  "{FILE_HASH}" -> "{DOMAIN_2}" [label="Embeds"];
  "{DOMAIN_1}" -> "{IP}" [label="Resolves To"];
  "{DOMAIN_2}" -> "{IP}" [label="Resolves To"];
}}'''

    ok, reasons = validate_dot(annotated, allowed_nodes, allowed_edges)
    assert ok, reasons


def test_validate_dot_accepts_edge_chain_of_real_edges():
    """`a -> b -> c` must expand to its pairwise edges, not be missed or mangled."""
    cache = _build_cache()
    node_details, _scored, diagram_edges, _skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    chained = (
        f'digraph AttackChain {{\n'
        f'  "{FILE_HASH}" -> "{DOMAIN_1}" -> "{IP}" [label="chain"];\n'
        f'}}'
    )
    ok, reasons = validate_dot(chained, allowed_nodes, allowed_edges)
    assert ok, reasons

    # And a chain that smuggles in a non-existent hop must still be rejected.
    bad_chain = (
        f'digraph AttackChain {{\n'
        f'  "{FILE_HASH}" -> "{DOMAIN_1}" -> "invented.example" [label="chain"];\n'
        f'}}'
    )
    ok, reasons = validate_dot(bad_chain, allowed_nodes, allowed_edges)
    assert not ok
    assert any("invented.example" in r for r in reasons)


# ---------------------------------------------------------------------------
# parse_dot_structure: label content must never look like nodes/edges
# ---------------------------------------------------------------------------

def test_parse_dot_structure_ignores_label_content():
    dot = (
        'digraph G {\n'
        '  node [shape=box, style=filled, fillcolor=lightgray, fontname="Arial"];\n'
        '  "A" -> "B" [label="weird -> \\"quoted words\\" inside a label"];\n'
        '}\n'
    )
    node_ids, edges = parse_dot_structure(dot)
    assert node_ids == {"A", "B"}
    assert edges == {("A", "B")}


# ---------------------------------------------------------------------------
# extract_dot_block / replace_dot_block
# ---------------------------------------------------------------------------

def test_extract_dot_block_tolerates_crlf_and_trailing_space():
    """
    A missed fence is not benign: the frontend's markdown parser normalises
    CRLF and trailing info-line whitespace and would render the block anyway,
    so the backend would validate nothing while unvalidated DOT reached
    d3-graphviz — and replace_dot_block would append a duplicate section.
    """
    assert extract_dot_block("t\r\n```dot\r\ndigraph G { }\r\n```\r\n") == "digraph G { }"
    assert extract_dot_block("t\n```dot \ndigraph G { }\n```\n") == "digraph G { }"


def test_extract_dot_block_ignores_non_dot_language_tags():
    """
    ```DOT / ```graphviz are invisible to the frontend too (it checks
    `match[1] === 'dot'`), so returning None here is correct — the caller then
    appends a real ```dot block, which is the repair rather than a miss.
    """
    assert extract_dot_block("```DOT\ndigraph G { }\n```") is None
    assert extract_dot_block("```graphviz\ndigraph G { }\n```") is None


def test_extract_dot_block_returns_none_without_fence():
    assert extract_dot_block("# Report\n\nNo diagram here.\n") is None


def test_extract_dot_block_returns_body_with_other_fences_present():
    markdown = (
        "# Report\n\n"
        "```json\n"
        '{"not": "dot"}\n'
        "```\n\n"
        "### 5. Attack Flow Diagram\n\n"
        "```dot\n"
        'digraph AttackChain { "a" -> "b"; }\n'
        "```\n\n"
        "### 6. Notes\n"
    )
    body = extract_dot_block(markdown)
    assert body == 'digraph AttackChain { "a" -> "b"; }'


def test_replace_dot_block_swaps_existing_block_in_place():
    markdown = (
        "# Report\n\n"
        "```dot\n"
        "digraph OldPlaceholder { }\n"
        "```\n\n"
        "### 6. Notes\nSome trailing content.\n"
    )
    new_dot = 'digraph AttackChain { "a" -> "b" [label="x"]; }'
    result = replace_dot_block(markdown, new_dot)

    assert new_dot in result
    assert "OldPlaceholder" not in result
    assert "### 6. Notes\nSome trailing content." in result
    assert result.count("```dot") == 1


def test_replace_dot_block_appends_section_when_absent():
    markdown = "# Report\n\nNo diagram section here.\n"
    new_dot = 'digraph AttackChain { "a" -> "b"; }'
    result = replace_dot_block(markdown, new_dot)

    assert markdown in result
    assert "### 5. Attack Flow Diagram" in result
    assert f"```dot\n{new_dot}\n```" in result


def test_replace_dot_block_handles_backslashes_in_replacement():
    """re.sub treats backslashes specially in string replacements; the DOT we
    substitute in routinely contains literal '\\n' (line-break) sequences and
    must survive untouched."""
    markdown = "```dot\nold\n```\n"
    new_dot = 'digraph G { "a" [label="FILE\\nabc123"]; }'
    result = replace_dot_block(markdown, new_dot)
    assert new_dot in result


# ---------------------------------------------------------------------------
# _select_diagram_edges
# ---------------------------------------------------------------------------

def test_select_diagram_edges_dedups_and_caps_preserving_order():
    scored = []
    # Five distinct root-adjacent edges (as _score_edges would sort them: first).
    for i in range(5):
        scored.append({"source": "root", "target": f"n{i}", "relationship": "rel"})
    # A duplicate of the first edge (same source/target/relationship) — must be dropped.
    scored.append({"source": "root", "target": "n0", "relationship": "rel"})
    # 50 more non-root edges that would exceed a small cap.
    for i in range(50):
        scored.append({"source": f"a{i}", "target": f"b{i}", "relationship": "rel2"})

    selected = _select_diagram_edges(scored, limit=10)

    assert len(selected) == 10
    # Root-adjacent edges (first in _score_edges order) all survive, in order.
    assert selected[:5] == scored[:5]
    # The duplicate did not consume a cap slot; the very next unique entries continue in order.
    assert selected[5]["source"] == "a0"
    assert selected[6]["source"] == "a1"


def test_select_diagram_edges_respects_default_limit_constant():
    scored = [
        {"source": f"s{i}", "target": f"t{i}", "relationship": "rel"}
        for i in range(DIAGRAM_EDGE_LIMIT + 25)
    ]
    selected = _select_diagram_edges(scored)
    assert len(selected) == DIAGRAM_EDGE_LIMIT
    assert selected == scored[:DIAGRAM_EDGE_LIMIT]


# ---------------------------------------------------------------------------
# End-to-end: generate_final_report_llm's extract -> validate -> fallback step.
#
# This is the integration the unit tests above can't cover — it exercises the
# real synthesis function against a stub LLM, verifying that a faithful
# annotation survives untouched, an invented one is replaced by the skeleton,
# and a missing fence still yields a diagram. It also asserts the skeleton
# actually reached the prompt, which is the whole premise of the task.
# ---------------------------------------------------------------------------

def _synthesis_state():
    return {
        "ioc": FILE_HASH,
        "job_id": "job-test",
        "specialist_results": {"malware": {"verdict": "Malicious", "summary": "s"}},
        "metadata": {},
    }


def _report_with_dot(dot_body: str) -> str:
    return f"# Final Report\n\n### 5. Attack Flow Diagram\n\n```dot\n{dot_body}\n```\n"


def test_synthesis_keeps_faithful_annotation():
    cache = _build_cache()
    node_details, _scored, diagram_edges, _skeleton = _pipeline(cache)

    edge_lines = "\n".join(
        f'  "{e["source"]}" -> "{e["target"]}" [label="Annotated {e["relationship"]}"];'
        for e in diagram_edges
    )
    annotated = (
        "digraph AttackChain {\n"
        "  rankdir=TB;\n"
        '  fontcolor="navy";\n'
        '  subgraph cluster_delivery { label="Delivery"; }\n'
        f"{edge_lines}\n"
        "}"
    )

    llm = _StubLLM(_report_with_dot(annotated))
    report = asyncio.run(generate_final_report_llm(_synthesis_state(), llm, cache=cache))

    kept = extract_dot_block(report)
    assert "Annotated" in kept, "faithful annotation was discarded"
    assert "cluster_delivery" in kept


def test_synthesis_falls_back_when_llm_invents_a_node():
    cache = _build_cache()
    node_details, _scored, diagram_edges, _skeleton = _pipeline(cache)

    invented = (
        "digraph AttackChain {\n"
        f'  "{FILE_HASH}" -> "attacker-owned.invalid" [label="fabricated"];\n'
        "}"
    )

    llm = _StubLLM(_report_with_dot(invented))
    report = asyncio.run(generate_final_report_llm(_synthesis_state(), llm, cache=cache))

    result = extract_dot_block(report)
    assert "attacker-owned.invalid" not in result
    # The skeleton's real entities are present instead.
    assert FILE_HASH in result and IP in result


def test_synthesis_appends_skeleton_when_llm_emits_no_diagram():
    cache = _build_cache()
    llm = _StubLLM("# Final Report\n\nNo diagram was produced.\n")
    report = asyncio.run(generate_final_report_llm(_synthesis_state(), llm, cache=cache))

    result = extract_dot_block(report)
    assert result is not None and "digraph AttackChain" in result


def test_synthesis_prompt_carries_the_skeleton():
    cache = _build_cache()
    llm = _StubLLM(_report_with_dot("digraph AttackChain { }"))
    asyncio.run(generate_final_report_llm(_synthesis_state(), llm, cache=cache))

    human_message = llm.captured[1].content
    assert "Attack Flow Diagram Skeleton" in human_message
    # Full, untruncated ids must reach the model — the bug the old
    # display-label grounding caused.
    assert FILE_HASH in human_message


# ---------------------------------------------------------------------------
# URL entity ids: found in review of S4-T5.
#
# parse_dot_structure stripped `//` comments with a regex, so a URL node id
# ("http://evil.example/p") had the rest of its line eaten, destroying the
# quote balance and leaving fragments like "http" and " -> " that read as
# invented nodes. The skeleton then failed to validate against ITSELF, so every
# report whose diagram contained a URL silently discarded the LLM's annotation
# and fell back to the bare skeleton. contacted_urls / embedded_urls / urls are
# all in triage's PRIORITY_RELATIONSHIPS, so this was most real hunts.
# ---------------------------------------------------------------------------

URL_ID = "http://u1.example.com/payload.bin"


def _build_cache_with_url() -> InvestigationCache:
    cache = _build_cache()
    cache.add_entity(URL_ID, "url", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 88}},
        "last_analysis_stats": {"malicious": 14},
    })
    cache.add_relationship(FILE_HASH, URL_ID, "contacted_urls")
    return cache


def test_parse_dot_structure_keeps_url_ids_intact():
    nodes, edges = parse_dot_structure(
        f'digraph G {{ "{FILE_HASH}" -> "{URL_ID}" [label="contacted_urls"]; }}'
    )
    assert URL_ID in nodes, sorted(nodes)
    assert (FILE_HASH, URL_ID) in edges
    # No fragments from the eaten line.
    assert "http" not in nodes
    assert not any(n.strip() == "->" for n in nodes)


def test_skeleton_with_a_url_node_validates_against_itself():
    """If the skeleton can't validate itself, the annotation step is dead."""
    cache = _build_cache_with_url()
    node_details, _scored, diagram_edges, skeleton = _pipeline(cache)
    allowed_nodes, allowed_edges = _allowed_sets(node_details, diagram_edges, FILE_HASH)

    assert URL_ID in skeleton
    ok, reasons = validate_dot(skeleton, allowed_nodes, allowed_edges)
    assert ok, reasons


def test_real_comments_are_still_stripped_alongside_urls():
    """The comment stripper must stay quote-aware in both directions."""
    dot = (
        f'digraph G {{\n'
        f'  // see http://reference.example/notes for context\n'
        f'  /* block comment with "quoted" text and http://x.example/y */\n'
        f'  "{FILE_HASH}" -> "{URL_ID}" [label="contacted_urls"];  # trailing\n'
        f'}}'
    )
    nodes, edges = parse_dot_structure(dot)
    assert nodes == {FILE_HASH, URL_ID}, sorted(nodes)
    assert edges == {(FILE_HASH, URL_ID)}
