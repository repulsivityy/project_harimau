"""
Tests for S4-T5 (Synthesis quality — complete edge attributes).

Background: the synthesis LLM used to see every edge twice under two
different identifier spaces with two different attribute sets — the
"Key Edges" block inside _build_graph_summary (keyed on entity ids, carrying
target_verdict/target_malicious_vendors, filtered to
has_threat_signal-and-qualifiers) and the "Machine-Readable Edge Reference"
from _build_edge_tuples (keyed on display labels, carrying only the
relationship name). Neither carried source_type/target_type, even though
_score_edges already computed both as locals and threw them away.

This suite covers the consolidation: _build_edge_tuples is now the single
edge fact table, keyed on entity ids (matching the DOT skeleton), carrying
the full attribute set (source/target type, verdict, threat_score — rendered
as "unknown" rather than a misleading 0 when GTI supplied no score —
malicious_vendors, and a high_signal flag), and the "Key Edges" section of
_build_graph_summary is gone.

Plain pytest, no pytest-asyncio dependency — the end-to-end test drives
generate_final_report_llm with asyncio.run and a stub LLM. Modeled on (but
does not import from) backend/tests/test_dot_builder.py.
"""

import asyncio

from backend.utils.graph_cache import InvestigationCache
from backend.utils.dot_builder import build_dot_skeleton, parse_dot_structure
from backend.agents.lead_hunter_synthesis import (
    _compute_node_details,
    _compute_high_signal,
    _score_edges,
    _select_diagram_edges,
    _build_edge_tuples,
    _build_graph_summary,
    _is_high_signal_edge,
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
# Fixture: one root file, one directly-scored domain, one directly-scored IP,
# and one descriptor-only pivot domain with NO gti_assessment at all (the
# common shape for entities discovered via a relationship-listing tool that
# GTI's own docstrings require to be called with descriptors_only=True — see
# extract_gti_summary's docstring in backend/utils/graph_cache.py).
# ---------------------------------------------------------------------------

FILE_HASH = "b" * 64
DOMAIN_1 = "c2.example.com"          # fully scored, root-adjacent
PIVOT_DOMAIN = "pivot.example.net"   # descriptor-only, no gti_assessment
IP = "198.51.100.9"                  # fully scored, non-root-adjacent


def _build_cache() -> InvestigationCache:
    cache = InvestigationCache()
    cache.add_entity(FILE_HASH, "file", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 90}},
        "meaningful_name": "invoice_2024.exe",
    })
    cache.add_entity(DOMAIN_1, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 85}},
    })
    # Descriptor-only pivot: no gti_assessment key at all, but a real
    # last_analysis_stats (which extract_gti_summary can carry independently
    # of gti_assessment) so it can pick up qualifiers without ever having a
    # GTI threat score.
    cache.add_entity(PIVOT_DOMAIN, "domain", {
        "last_analysis_stats": {"malicious": 10},
    })
    cache.add_entity(IP, "ip_address", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 95}},
    })

    cache.add_relationship(FILE_HASH, DOMAIN_1, "contacted_domains")       # root-adjacent
    cache.add_relationship(FILE_HASH, PIVOT_DOMAIN, "embedded_domains")   # root-adjacent, malware<->infra bridge
    cache.add_relationship(DOMAIN_1, IP, "resolutions")                   # non-root-adjacent
    cache.add_relationship(PIVOT_DOMAIN, IP, "network_location")          # non-root-adjacent
    return cache


def _pipeline(cache: InvestigationCache, root_ioc: str = FILE_HASH, force_high_signal=frozenset()):
    """
    Run the same node_details -> high_signal -> scored_edges -> diagram_edges
    chain generate_final_report_llm runs.

    `force_high_signal` lets a test manually widen the high-signal set beyond
    what _compute_high_signal would naturally derive — needed because that
    function's qualifying formula (score >= 80, or score > 60 AND
    qualifiers >= 2) can never fire for a descriptor-only node whose score is
    coerced to 0 for arithmetic safety, regardless of how many
    malicious-count/relationship/bridge qualifiers it has. _build_graph_summary
    and _score_edges both accept a precomputed high_signal_node_ids override
    for exactly this reason.
    """
    node_details = _compute_node_details(cache)
    high_signal_node_ids, _ir, _b = _compute_high_signal(cache, node_details)
    high_signal_node_ids = high_signal_node_ids | set(force_high_signal)
    scored_edges = _score_edges(cache, node_details, high_signal_node_ids, root_ioc)
    diagram_edges = _select_diagram_edges(scored_edges)
    return node_details, high_signal_node_ids, scored_edges, diagram_edges


def _find_line(text: str, *needles: str) -> str:
    """Return the first line of `text` containing all `needles`, or ''."""
    for line in text.splitlines():
        if all(n in line for n in needles):
            return line
    return ""


# ---------------------------------------------------------------------------
# _compute_node_details: score vs score_known
# ---------------------------------------------------------------------------

def test_score_known_distinguishes_missing_score_from_zero_score():
    cache = _build_cache()
    node_details = _compute_node_details(cache)

    pivot = node_details[PIVOT_DOMAIN]
    assert pivot["score_known"] is False
    assert pivot["score"] == 0
    assert isinstance(pivot["score"], int)

    scored = node_details[DOMAIN_1]
    assert scored["score_known"] is True
    assert scored["score"] == 85


# ---------------------------------------------------------------------------
# _build_edge_tuples: the fact table
# ---------------------------------------------------------------------------

def test_fact_table_line_carries_full_attribute_set():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, diagram_edges = _pipeline(cache)

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    line = _find_line(table, FILE_HASH, DOMAIN_1, "contacted_domains")
    assert line, table
    # Assert the *fields*, not bare substrings: `assert "domain" in line` was
    # satisfied by the relationship name "contacted_domains" rather than by the
    # target's type, so dropping target_type entirely still passed.
    source_part, _, target_part = line.partition("-[contacted_domains]->")
    assert target_part, line
    assert FILE_HASH in source_part
    assert "(file," in source_part
    assert "verdict=malicious" in source_part
    assert "threat_score=" in source_part
    assert DOMAIN_1 in target_part
    assert "(domain," in target_part
    assert "verdict=malicious" in target_part
    assert "malicious_vendors=" in target_part
    assert "high_signal=" in target_part


def test_fact_table_carries_source_verdict_independently_of_target():
    """
    source_verdict had no real coverage: the fixture's source and target were
    both malicious, so an assertion on "verdict=malicious" was satisfied by the
    target alone and dropping source_verdict still passed.
    """
    cache = InvestigationCache()
    benign_src = "benign-src.example"
    cache.add_entity(benign_src, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_BENIGN"}, "threat_score": {"value": 3}},
    })
    cache.add_entity(IP, "ip_address", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 95}},
        "last_analysis_stats": {"malicious": 20},
    })
    cache.add_relationship(benign_src, IP, "resolutions")

    node_details, high_signal_node_ids, scored_edges, _de = _pipeline(cache, root_ioc=benign_src)
    table = _build_edge_tuples(
        {"ioc": benign_src}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    line = _find_line(table, benign_src, IP, "resolutions")
    source_part, _, target_part = line.partition("-[resolutions]->")
    assert "verdict=benign" in source_part, source_part
    assert "verdict=malicious" in target_part, target_part


def test_fact_table_emits_label_only_when_it_differs_from_the_id():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _de = _pipeline(cache)
    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    line = _find_line(table, FILE_HASH, DOMAIN_1, "contacted_domains")
    source_part, _, target_part = line.partition("-[contacted_domains]->")
    # The file has a meaningful_name that differs from its hash -> labelled.
    assert 'label="' in source_part, source_part
    # The domain's label equals its id -> no redundant label field.
    assert 'label="' not in target_part, target_part


def test_fact_table_renders_unknown_score_not_zero_for_descriptor_only_target():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, diagram_edges = _pipeline(cache)

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    line = _find_line(table, FILE_HASH, PIVOT_DOMAIN, "embedded_domains")
    assert line, table
    assert "threat_score=unknown" in line
    assert "threat_score=0" not in line


def test_fact_table_ids_are_covered_by_dot_skeleton_node_set():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, diagram_edges = _pipeline(cache)
    skeleton = build_dot_skeleton(node_details, diagram_edges, FILE_HASH)
    parsed_nodes, _parsed_edges = parse_dot_structure(skeleton)

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    endpoint_ids = {edge["source"] for edge in diagram_edges} | {edge["target"] for edge in diagram_edges}
    for entity_id in endpoint_ids:
        assert entity_id in table
        assert entity_id in parsed_nodes


def test_fact_table_relevance_ordering_root_adjacent_first():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _diagram_edges = _pipeline(cache)

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    root_adjacent_pos = table.index("[contacted_domains]")
    non_root_adjacent_pos = table.index("[resolutions]")
    assert root_adjacent_pos < non_root_adjacent_pos


# ---------------------------------------------------------------------------
# _build_graph_summary: "Key Edges" is gone, folded into the fact table
# ---------------------------------------------------------------------------

def test_graph_summary_no_longer_has_key_edges_section():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _diagram_edges = _pipeline(cache)

    summary = _build_graph_summary(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    assert "Key Edges" not in summary


def test_edges_qualifying_for_old_key_edges_filter_are_in_fact_table_as_high_signal():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _diagram_edges = _pipeline(cache)

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    # Same predicate the old (now-removed) "Key Edges" block used.
    qualifying = [e for e in scored_edges if e["has_threat_signal"] and e["qualifiers"] >= 1]
    assert qualifying, "fixture should produce at least one qualifying edge"
    for edge in qualifying:
        line = _find_line(table, edge["source"], edge["target"], f'[{edge["relationship"]}]')
        assert line, f"missing fact-table line for {edge['source']} -> {edge['target']}"
        assert "high_signal=yes" in line


def test_graph_summary_renders_unknown_score_for_high_signal_node_lacking_score():
    """
    Construct a node that qualifies as high-signal via the
    malicious_count/relationship/bridge qualifiers (not via score — its score
    is unknown/coerced to 0) by forcing it into high_signal_node_ids, then
    assert the High-Signal Nodes line renders threat_score=unknown rather
    than 0.
    """
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _diagram_edges = _pipeline(
        cache, force_high_signal={PIVOT_DOMAIN}
    )
    assert node_details[PIVOT_DOMAIN]["score_known"] is False

    summary = _build_graph_summary(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    line = _find_line(summary, PIVOT_DOMAIN)
    assert line, summary
    assert "threat_score=unknown" in line
    assert "threat_score=0" not in line


# ---------------------------------------------------------------------------
# End-to-end: generate_final_report_llm context assembly
# ---------------------------------------------------------------------------

def _synthesis_state():
    return {
        "ioc": FILE_HASH,
        "job_id": "job-test-s4t5",
        "specialist_results": {"malware": {"verdict": "Malicious", "summary": "s"}},
        "metadata": {},
    }


def test_synthesis_context_relabels_fact_table_and_drops_key_edges():
    cache = _build_cache()
    llm = _StubLLM("# Final Report\n\n```dot\ndigraph AttackChain { }\n```\n")
    asyncio.run(generate_final_report_llm(_synthesis_state(), llm, cache=cache))

    human_message = llm.captured[1].content
    assert "Graph Edge Facts" in human_message
    assert "Machine-Readable Edge Reference" not in human_message
    assert "Key Edges" not in human_message


# ---------------------------------------------------------------------------
# Regressions found reviewing this change. The "qualifying edges are in the
# fact table" test above uses a 4-edge fixture, so it is below the 40-edge cap
# and the property holds trivially — it cannot detect the loss below.
# ---------------------------------------------------------------------------

def _build_wide_root_cache(noise_edges: int = 45, distant_malicious: int = 6):
    """
    The shape a real multi-pivot hunt produces: a malicious root with many
    benign root-adjacent edges, plus confirmed-malicious infrastructure a hop
    or two out.

    triage.py adds a root->entity edge for every entity returned across 13
    PRIORITY_RELATIONSHIPS at limit=10 (signal_filter only prunes the LLM's
    prompt list, not the graph), so a root with 40+ adjacent edges is normal.
    """
    cache = InvestigationCache()
    cache.add_entity(FILE_HASH, "file", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 90}},
        "last_analysis_stats": {"malicious": 50},
    })
    for i in range(noise_edges):
        domain = f"cdn{i}.benign.example"
        cache.add_entity(domain, "domain", {
            "gti_assessment": {"verdict": {"value": "VERDICT_UNDETECTED"}, "threat_score": {"value": 0}},
            "last_analysis_stats": {"malicious": 0},
        })
        cache.add_relationship(FILE_HASH, domain, "contacted_domains")

    cache.add_entity("hop.example", "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_UNDETECTED"}, "threat_score": {"value": 10}},
    })
    cache.add_relationship(FILE_HASH, "hop.example", "contacted_domains")
    for i in range(distant_malicious):
        ip = f"198.51.100.{i + 1}"
        cache.add_entity(ip, "ip_address", {
            "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 95}},
            "last_analysis_stats": {"malicious": 12},
        })
        cache.add_relationship("hop.example", ip, "resolutions")
    return cache


def test_high_signal_edges_survive_the_cap_past_a_wide_root():
    """
    The regression this change introduced by folding "Key Edges" (its own
    filtered budget of 25) into the diagram's unfiltered 40-edge cap.

    _score_edges sorts root_adjacent first and derives node_score from
    max(source, target), so a malicious root hands its own high score to every
    one of its edges — including edges to benign zero-detection CDN domains.
    Those then outrank confirmed-malicious infrastructure further out. Measured
    before the fix: 0 of 6 high-signal edges survived; the LLM saw 40 benign
    CDN edges and no malicious infrastructure at all.
    """
    cache = _build_wide_root_cache()
    node_details, high_signal_node_ids, scored_edges, diagram_edges = _pipeline(cache)

    expected = [e for e in scored_edges if _is_high_signal_edge(e)]
    assert expected, "fixture should produce high-signal edges"

    selected_keys = {(e["source"], e["target"], e["relationship"]) for e in diagram_edges}
    missing = [e for e in expected
               if (e["source"], e["target"], e["relationship"]) not in selected_keys]
    assert not missing, f"{len(missing)} of {len(expected)} high-signal edges evicted by the cap"

    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    assert table.count("high_signal=yes") == len(expected)
    # Root context is still represented rather than crowded out entirely.
    assert table.count("high_signal=no") > 0
    assert len(table.strip().splitlines()) == DIAGRAM_EDGE_LIMIT


def test_cap_is_still_respected_when_high_signal_edges_exceed_it():
    cache = _build_wide_root_cache(noise_edges=5, distant_malicious=60)
    _nd, _hs, _se, diagram_edges = _pipeline(cache)
    assert len(diagram_edges) == DIAGRAM_EDGE_LIMIT


def test_labels_cannot_inject_extra_fact_table_rows():
    """
    Labels are attacker-chosen (meaningful_name is the filename the malware
    author picked). A newline in one would render as an additional, fully
    formed fact-table row — fabricating a high-signal edge between entities
    that don't exist in the graph.
    """
    cache = InvestigationCache()
    hostile = (
        'x" (file, verdict=malicious, threat_score=100) '
        '-[dropped_files]-> fabricated.example.com (domain, verdict=malicious, '
        'threat_score=100, malicious_vendors=99) | high_signal=yes\n'
        '- 9.9.9.9'
    )
    cache.add_entity(FILE_HASH, "file", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 90}},
        "meaningful_name": hostile,
    })
    cache.add_entity(DOMAIN_1, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 70}},
        "last_analysis_stats": {"malicious": 8},
    })
    cache.add_relationship(FILE_HASH, DOMAIN_1, "contacted_domains")

    node_details, high_signal_node_ids, scored_edges, _de = _pipeline(cache)
    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )

    # One edge in the graph must render as exactly one line.
    assert len(table.strip().splitlines()) == 1, table
    assert "fabricated.example.com" not in table or table.count("\n") == 0
    # The same guarantee for the graph summary's label field.
    summary = _build_graph_summary(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    assert "\n- 9.9.9.9" not in summary


def test_string_threat_score_is_coerced_not_left_as_str():
    """
    GTI has returned the score as a string. Left as str it reaches
    _compute_high_signal's `>= 80` and sorted(key=(score, ...)) and raises
    TypeError — the sibling of the {"value": None} crash in CHANGELOG 0.6.1.
    """
    cache = InvestigationCache()
    cache.add_entity(DOMAIN_1, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": "85"}},
    })
    node_details = _compute_node_details(cache)
    node = node_details[DOMAIN_1]
    assert node["score"] == 85
    assert isinstance(node["score"], (int, float)) and not isinstance(node["score"], str)
    assert node["score_known"] is True
    # Must not raise.
    _compute_high_signal(cache, node_details)


def test_unparseable_threat_score_falls_back_to_unknown():
    cache = InvestigationCache()
    cache.add_entity(DOMAIN_1, "domain", {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": "high"}},
    })
    node = _compute_node_details(cache)[DOMAIN_1]
    assert node["score"] == 0 and isinstance(node["score"], int)
    assert node["score_known"] is False


def test_integral_scores_render_without_a_decimal_point():
    cache = _build_cache()
    node_details, high_signal_node_ids, scored_edges, _de = _pipeline(cache)
    table = _build_edge_tuples(
        {"ioc": FILE_HASH}, cache,
        node_details=node_details,
        high_signal_node_ids=high_signal_node_ids,
        scored_edges=scored_edges,
    )
    assert ".0" not in table, table
