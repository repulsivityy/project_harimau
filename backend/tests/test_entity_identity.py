"""Focused invariants for typed IOC identity and GTI URL aliases."""

import networkx as nx

from backend.utils.entity_identity import gti_url_id, normalise_entity_id, normalise_target_id
from backend.utils.graph_cache import InvestigationCache
from backend.utils.target_outcomes import assess_target_outcomes


URL = "HTTPS://Example.TEST/CaseSensitive/Path?Token=AbC"
CANONICAL_URL = "https://example.test/CaseSensitive/Path?Token=AbC"


def test_url_identity_only_casefolds_scheme_and_host():
    assert normalise_entity_id(URL) == CANONICAL_URL
    assert normalise_entity_id("https://example.test/casesensitive/Path?Token=AbC") != CANONICAL_URL
    assert normalise_entity_id("ABCDEF" * 10, "file") == ("abcdef" * 10)
    assert normalise_entity_id("MiXeD.Example.TEST", "domain") == "mixed.example.test"


def test_gti_url_id_and_raw_tool_target_resolve_to_one_graph_node():
    cache = InvestigationCache()
    url_id = gti_url_id(URL)
    cache.add_entity(url_id, "url", {"url": URL})
    cache.add_relationship("sample" * 11, url_id, "contacted_urls")

    assert list(cache.graph.nodes) == [CANONICAL_URL, "sample" * 11]
    assert cache.has_entity(URL)
    assert cache.get_entity_full(URL)["gti_id"] == url_id
    assert cache.graph.has_edge("sample" * 11, CANONICAL_URL)


def test_url_tool_provenance_requires_the_same_case_sensitive_target():
    selected = [CANONICAL_URL]
    outcomes = assess_target_outcomes(
        selected,
        {"analyzed_targets": [{"indicator": "https://example.test/casesensitive/Path?Token=AbC", "notes": "wrong resource"}]},
        "infrastructure",
    )
    assert outcomes[f"infrastructure:{CANONICAL_URL}"]["reason"] == "not_addressed_by_model"


def test_url_target_keeps_terminal_punctuation_but_domain_prose_does_not():
    assert normalise_target_id(f"{URL}.") == f"{CANONICAL_URL}."
    assert normalise_target_id("Example.TEST.") == "example.test"


def test_deserializing_legacy_url_aliases_rewrites_edges_to_one_node():
    """A checkpoint may contain both an old lowercased key and GTI-id edge."""
    legacy_key = "https://example.test/casesensitive/path?token=abc"
    url_id = gti_url_id(URL)
    legacy = nx.MultiDiGraph()
    legacy.add_node("root", entity_type="file")
    legacy.add_node(legacy_key, entity_type="url", url=URL)
    legacy.add_edge("root", url_id, relationship="contacted_urls")

    cache = InvestigationCache(nx.node_link_data(legacy))
    assert set(cache.graph.nodes) == {"root", CANONICAL_URL}
    assert cache.graph.has_edge("root", CANONICAL_URL)
