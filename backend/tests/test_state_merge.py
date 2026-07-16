"""
Tests for the `metadata` state-field reducer (backend/graph/state.py).

Regression coverage for a real bug: malware_node and infrastructure_node run
as genuine parallel LangGraph branches fanned out from `gate`. Both write into
state["metadata"]["rich_intel"]["relationships"] (under different rel_name
keys) via push_to_rich_intel. The old reducer, `merge_dicts` (a shallow
`{**a, **b}`), let whichever branch's update got folded in second silently
replace the other's entire `rich_intel` sub-tree - discarding real findings.
`merge_metadata` replaces it with a recursive deep-merge that also dedupes
rich_intel.relationships entity lists on the same (id, source_id) key
push_to_rich_intel itself uses.

NOTE on importability: backend/graph/state.py does
`from langchain_core.messages import BaseMessage` at module scope purely for
a type annotation - it's never invoked at runtime. `langchain_core` is not
installed in this environment (verified: `python3 -c "import langchain_core"`
raises ModuleNotFoundError). Rather than skip testing the real code, we
install a minimal stand-in module into sys.modules (only if the real package
isn't already importable) so `backend.graph.state` imports cleanly and we're
exercising the actual merge_metadata implementation, not a re-implementation.
"""
import sys
import types

try:
    import langchain_core.messages  # noqa: F401
except ImportError:
    fake_lc_core = types.ModuleType("langchain_core")
    fake_lc_messages = types.ModuleType("langchain_core.messages")

    class _FakeBaseMessage:
        pass

    fake_lc_messages.BaseMessage = _FakeBaseMessage
    sys.modules.setdefault("langchain_core", fake_lc_core)
    sys.modules.setdefault("langchain_core.messages", fake_lc_messages)

from backend.graph.state import merge_metadata

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  OK  ' if cond else ' FAIL '} {name} {detail if not cond else ''}")


print("=" * 70)
print("metadata reducer (merge_metadata) - parallel specialist merge")
print("=" * 70)

def entity(id_, type_, source_id, **attrs):
    return {"id": id_, "type": type_, "source_id": source_id, "attributes": attrs}


# --- (a) different rel_name keys on each side must both survive ---
malware_meta = {
    "risk_level": "Assessing...",
    "gti_score": 80,
    "rich_intel": {
        "triage_summary": "some summary",
        "relationships": {
            "communicates_with": [entity("evil-c2.top", "domain", "abc123")],
            "dropped": [entity("d" * 64, "file", "abc123", meaningful_name="payload.exe")],
        },
    },
}
infra_meta = {
    "risk_level": "Assessing...",
    "gti_score": 80,
    "rich_intel": {
        "triage_summary": "some summary",
        "relationships": {
            "related_infrastructure": [entity("1.2.3.4", "ip_address", "abc123")],
        },
    },
}

merged = merge_metadata(malware_meta, infra_meta)
rels = merged["rich_intel"]["relationships"]
check(
    "different rel_name keys: malware's communicates_with survives",
    "communicates_with" in rels and len(rels["communicates_with"]) == 1,
    f"got {rels.get('communicates_with')}",
)
check(
    "different rel_name keys: malware's dropped survives",
    "dropped" in rels and len(rels["dropped"]) == 1,
    f"got {rels.get('dropped')}",
)
check(
    "different rel_name keys: infra's related_infrastructure survives",
    "related_infrastructure" in rels and len(rels["related_infrastructure"]) == 1,
    f"got {rels.get('related_infrastructure')}",
)
check(
    "non-rich_intel sibling scalar keys preserved (risk_level)",
    merged.get("risk_level") == "Assessing...",
)
check(
    "rich_intel sibling key (triage_summary) preserved through merge",
    merged["rich_intel"].get("triage_summary") == "some summary",
)


# --- (b) same rel_name key, different (non-overlapping) entities: concatenated ---
a = {"rich_intel": {"relationships": {"communicates_with": [entity("x.com", "domain", "src1")]}}}
b = {"rich_intel": {"relationships": {"communicates_with": [entity("y.com", "domain", "src1")]}}}
merged_same_key = merge_metadata(a, b)
cw = merged_same_key["rich_intel"]["relationships"]["communicates_with"]
ids = {e["id"] for e in cw}
check(
    "same rel_name, non-overlapping entities: both present",
    ids == {"x.com", "y.com"} and len(cw) == 2,
    f"got {cw}",
)


# --- (c) same rel_name key, overlapping entity (same id+source_id): no duplicate ---
a2 = {"rich_intel": {"relationships": {"dropped": [entity("h" * 64, "file", "ioc1", meaningful_name="a.exe")]}}}
b2 = {"rich_intel": {"relationships": {"dropped": [entity("H" * 64, "file", "IOC1", meaningful_name="a.exe")]}}}
merged_overlap = merge_metadata(a2, b2)
dropped = merged_overlap["rich_intel"]["relationships"]["dropped"]
check(
    "overlapping entity (case-insensitive id+source_id): not duplicated",
    len(dropped) == 1,
    f"got {dropped}",
)

# A genuinely distinct entity sharing the same id but a different source_id
# must NOT be treated as a duplicate (dedup key is (id, source_id), not id alone).
a2b = {"rich_intel": {"relationships": {"dropped": [entity("h" * 64, "file", "ioc1")]}}}
b2b = {"rich_intel": {"relationships": {"dropped": [entity("h" * 64, "file", "ioc2")]}}}
merged_diff_source = merge_metadata(a2b, b2b)
dropped2 = merged_diff_source["rich_intel"]["relationships"]["dropped"]
check(
    "same id, different source_id: both kept (dedup key is id+source_id)",
    len(dropped2) == 2,
    f"got {dropped2}",
)


# --- (d) non-rich_intel top-level metadata key present only on one side ---
a3 = {"risk_level": "Malicious", "tool_call_trace": ["call1", "call2"]}
b3 = {"gti_score": 95}
merged_onesided = merge_metadata(a3, b3)
check(
    "one-sided top-level key (tool_call_trace) survives",
    merged_onesided.get("tool_call_trace") == ["call1", "call2"],
    f"got {merged_onesided}",
)
check(
    "one-sided top-level key (gti_score) survives",
    merged_onesided.get("gti_score") == 95,
)
check(
    "one-sided top-level key (risk_level) survives",
    merged_onesided.get("risk_level") == "Malicious",
)


# --- (e) idempotency: merging twice produces the same result as merging once ---
once = merge_metadata(malware_meta, infra_meta)
twice = merge_metadata(once, once)
check(
    "idempotent: re-merging the merged result is a no-op",
    once == twice,
    f"once={once}\ntwice={twice}",
)

# Idempotency should also hold when re-applying the *same pair* repeatedly
# (simulates a checkpointer replay folding in the same branch update twice).
replayed = merge_metadata(merge_metadata(malware_meta, infra_meta), infra_meta)
rels_replayed = replayed["rich_intel"]["relationships"]
check(
    "re-applying infra's update twice does not duplicate its entities",
    len(rels_replayed["related_infrastructure"]) == 1,
    f"got {rels_replayed['related_infrastructure']}",
)


# --- scalar last-write-wins semantics preserved for single-writer keys ---
pre_fanout = {"risk_level": "Assessing...", "gti_score": 80, "rich_intel": {}}
post_a = dict(pre_fanout)
post_b = {"risk_level": "Assessing...", "gti_score": 80, "rich_intel": {}}
merged_scalar = merge_metadata(post_a, post_b)
check(
    "identical scalar values on both sides merge without conflict",
    merged_scalar["risk_level"] == "Assessing..." and merged_scalar["gti_score"] == 80,
)


# --- None handling ---
check("merge_metadata(None, b) returns b", merge_metadata(None, {"x": 1}) == {"x": 1})
check("merge_metadata(a, None) returns a", merge_metadata({"x": 1}, None) == {"x": 1})
check("merge_metadata(None, None) returns {}", merge_metadata(None, None) == {})


print()
print("=" * 70)
print(f"PASSED {len(PASS)} / {len(PASS) + len(FAIL)}")
if FAIL:
    print("FAILURES:")
    [print("  -", f) for f in FAIL]


def test_metadata_merge():
    assert not FAIL, f"failed checks: {FAIL}"
