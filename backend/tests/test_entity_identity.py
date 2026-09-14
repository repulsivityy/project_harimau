"""Focused invariants for typed IOC identity and GTI URL aliases."""

import networkx as nx

from backend.utils.entity_identity import gti_url_id, normalise_entity_id, normalise_target_id
from backend.utils.graph_cache import InvestigationCache, extract_gti_summary
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


def test_opaque_non_base64_url_id_resolves_via_extract_gti_summary_attributes():
    """Some GTI relationship-descriptor payloads name a url object by an
    opaque id that isn't the base64url id gti_url_id() produces (e.g. a raw
    SHA256 hash), which normalise_entity_id cannot decode on its own.
    Infrastructure-/malware-specialist pivot discovery (get_entities_related_
    to_a_domain/_an_ip_address/_an_url, get_network_activity) build their
    add_entity attributes via extract_gti_summary(item), not a hand-built
    dict -- reproduce that exact shape (confirmed live against the real GTI
    API: a descriptors_only=True domain "urls" relationship still returns a
    full `attributes.url` field), rather than asserting a shape those call
    sites cannot actually produce.
    """
    opaque_id = "b" * 64
    descriptor_item = {
        "id": opaque_id,
        "type": "url",
        "attributes": {"url": URL, "last_analysis_stats": {"malicious": 5}},
    }
    attrs = {"infra_context": "domain_urls"}
    attrs.update(extract_gti_summary(descriptor_item))
    assert attrs.get("url") == URL  # extract_gti_summary must carry the field through

    cache = InvestigationCache()
    cache.add_entity(opaque_id, "url", attrs)
    cache.add_relationship("example.test", opaque_id, "urls")

    assert CANONICAL_URL in cache.graph.nodes
    assert f"gti-url:{opaque_id}" not in cache.graph.nodes
    assert cache.get_entity_full(opaque_id)["gti_id"] == opaque_id
    assert cache.graph.has_edge("example.test", CANONICAL_URL)


def test_url_root_entity_id_is_not_overridden_by_a_differently_spelled_url_attribute():
    """The root entity of a URL-rooted investigation is added with its own
    already-decodable id (state["ioc"]) plus GTI's full `attributes` block,
    which can carry a `url` field that differs in spelling (e.g. VT appends
    a trailing slash to a bare-host URL) without being a different resource.
    An already-decodable id must never be overridden by attributes -- only
    GTI's opaque, undecodable relationship-descriptor ids fall back to them.
    """
    root_id = "https://d.jennymodd.com"
    cache = InvestigationCache()
    cache.add_entity(root_id, "url", {"url": "https://d.jennymodd.com/"})

    assert root_id in cache.graph.nodes
    assert "https://d.jennymodd.com/" not in cache.graph.nodes


def test_last_final_url_is_not_used_as_a_live_identity_fallback():
    """last_final_url describes a redirect destination, not another spelling
    of this URL (per _canonical_url_node_id's own migration-path note) --
    an opaque id with only last_final_url (no `url`) must not be re-keyed
    onto the redirect target on the live add_entity path.
    """
    opaque_id = "c" * 64
    cache = InvestigationCache()
    cache.add_entity(opaque_id, "url", {"last_final_url": "https://redirect-dest.test/b"})

    assert "https://redirect-dest.test/b" not in cache.graph.nodes


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
