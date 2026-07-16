import time
from backend.utils.graph_cache import InvestigationCache, extract_gti_summary
from backend.utils.report_validator import validate_report_iocs, annotate_report
from backend.utils.verdict_engine import apply_composite_verdicts, compute_composite_verdict, build_escalation_context
from backend.utils.signal_filter import get_signal_reason, promote_by_graph_context, build_promotion_context

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

# build_promotion_context — simulates what lead_hunter.py does: write the
# promoted reason onto the node's signal_reason attr, then render for the
# synthesis prompt.
for entity_id, reason in promoted.items():
    g.graph.nodes[entity_id]["signal_reason"] = reason
promo_ctx = build_promotion_context(g)
check("promotion context renders promoted node id", "quiet-domain" in promo_ctx, f"got {promo_ctx}")
check("promotion context renders reason", "graph_context:" in promo_ctx, f"got {promo_ctx}")

empty_g = InvestigationCache()
empty_g.add_entity("solo", "domain", {})
check("no promotions renders placeholder",
      build_promotion_context(empty_g) == "No entities were promoted by graph-context analysis.")

heuristic_g = InvestigationCache()
heuristic_g.add_entity("new-domain", "domain", {"signal_reason": "newly_registered:4d"})
check("non-promotion signal_reason NOT rendered",
      "new-domain" not in build_promotion_context(heuristic_g), f"got {build_promotion_context(heuristic_g)}")

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

# --- Non-entity taxonomy nodes must never be escalated ---
# (MITRE technique / collection-attribution / resolution-join nodes have no
# gti_assessment; adjacency to malware alone must not turn them "suspicious".)
tax = InvestigationCache()
tax.add_entity("mal-root", "file", gti("VERDICT_MALICIOUS", 95, 50))
tax.add_entity("t1012", "attack_technique", {})
tax.add_entity("apt-collection", "collection", {})
tax.add_entity("some-resolution", "resolution", {})
tax.add_entity("real-domain", "domain", gti("VERDICT_UNDETECTED", 0, 0))
tax.add_relationship("mal-root", "t1012", "attack_techniques")
tax.add_relationship("mal-root", "apt-collection", "associations")
tax.add_relationship("mal-root", "some-resolution", "resolutions")
tax.add_relationship("mal-root", "real-domain", "contacted_domains")

r = compute_composite_verdict("t1012", tax)
check("attack_technique node adjacent to malicious NOT escalated", not r["escalated"], f"got {r}")
check("attack_technique node composite_verdict is sentinel (no verdict)", r["composite_verdict"] is None, f"got {r}")

r = compute_composite_verdict("apt-collection", tax)
check("collection node adjacent to malicious NOT escalated", not r["escalated"], f"got {r}")
check("collection node composite_verdict is sentinel (no verdict)", r["composite_verdict"] is None, f"got {r}")

r = compute_composite_verdict("some-resolution", tax)
check("resolution node adjacent to malicious NOT escalated", not r["escalated"], f"got {r}")
check("resolution node composite_verdict is sentinel (no verdict)", r["composite_verdict"] is None, f"got {r}")

r = compute_composite_verdict("real-domain", tax)
check("regression: real domain adjacent to malicious IS still escalated", r["escalated"], f"got {r}")
check("regression: real domain escalates to suspicious", r["composite_verdict"] == "suspicious", f"got {r}")

tax_stats = apply_composite_verdicts(tax, "taxonomy-test")
check("taxonomy nodes not counted as escalated", tax_stats["escalated"] == 1, f"got {tax_stats}")
check("attack_technique node gets no composite_verdict attr written",
      "composite_verdict" not in tax.graph.nodes["t1012"], f"{dict(tax.graph.nodes['t1012'])}")
check("collection node gets no composite_verdict attr written",
      "composite_verdict" not in tax.graph.nodes["apt-collection"])
check("resolution node gets no composite_verdict attr written",
      "composite_verdict" not in tax.graph.nodes["some-resolution"])

tax_ctx = build_escalation_context(tax)
check("escalation context does NOT render technique node", "t1012" not in tax_ctx, f"got {tax_ctx}")
check("escalation context does NOT render collection node", "apt-collection" not in tax_ctx, f"got {tax_ctx}")
check("escalation context does NOT render resolution node", "some-resolution" not in tax_ctx, f"got {tax_ctx}")

# --- Regression: an IP root must be typed "ip_address", not "ip" ---
# triage.py used to cache IP roots as entity_type="ip" (bare .lower() on GTI's
# "IP" type string), which would silently fall outside REAL_INDICATOR_TYPES
# and make every IP-rooted investigation's primary target unescalatable.
ip_root = InvestigationCache()
ip_root.add_entity("1.2.3.4", "ip_address", gti("VERDICT_UNDETECTED", 0, 0))
ip_root.add_entity("dropper", "file", gti("VERDICT_MALICIOUS", 90, 40))
ip_root.add_relationship("dropper", "1.2.3.4", "contacted_ips")
r = compute_composite_verdict("1.2.3.4", ip_root)
check("ip_address-typed root adjacent to malicious IS escalated", r["escalated"], f"got {r}")
check("ip_address-typed root escalates to suspicious", r["composite_verdict"] == "suspicious", f"got {r}")
check("escalation context DOES render the real escalated domain", "real-domain" in tax_ctx, f"got {tax_ctx}")

apply_composite_verdicts(c, "idem")
before = {n: c.graph.nodes[n]["composite_verdict"] for n in c.graph.nodes()}
apply_composite_verdicts(c, "idem2")
after = {n: c.graph.nodes[n]["composite_verdict"] for n in c.graph.nodes()}
check("idempotent (no cascade on re-run)", before == after, f"{before} vs {after}")

print(); print("="*70); print("#7 EXTRACT_GTI_SUMMARY"); print("="*70)

# --- Regression: the original 4-field extraction still works unchanged ---
rel_item_basic = {
    "id": "evil.example",
    "type": "domain",
    "attributes": {
        "gti_assessment": {"verdict": {"value": "VERDICT_MALICIOUS"}, "threat_score": {"value": 85}},
        "meaningful_name": "evil-payload.exe",
        "names": ["evil-payload.exe", "alt-name.bin"],
        "last_analysis_stats": {"malicious": 40, "suspicious": 2},
    },
}
s = extract_gti_summary(rel_item_basic)
check("regression: gti_assessment extracted", s.get("gti_assessment", {}).get("threat_score", {}).get("value") == 85, f"got {s}")
check("regression: meaningful_name extracted", s.get("meaningful_name") == "evil-payload.exe")
check("regression: names extracted", s.get("names") == ["evil-payload.exe", "alt-name.bin"])
check("regression: last_analysis_stats extracted", s.get("last_analysis_stats", {}).get("malicious") == 40)
check("regression: gti_id/gti_type carried through", s.get("gti_id") == "evil.example" and s.get("gti_type") == "domain")

# --- New fields ARE extracted when a richer attributes/context_attributes blob is present ---
rel_item_rich = {
    "id": "richdomain.example",
    "type": "domain",
    "attributes": {
        "malware_families": ["Emotet"],
        "related_threat_actors": ["APT29"],
        "associations": ["campaign-x"],
        "campaigns": ["campaign-x"],
        "sandbox_verdicts": {"Zenbox": {"category": "malicious"}},
        "behaviour_summary": {"processes_created": ["cmd.exe"]},
        "crowdsourced_ids_results": [{"rule": "ET MALWARE"}],
        "last_analysis_date": NOW,
        "creation_date": NOW - 5 * DAY,
        "tld": "xyz",
        "first_seen_itw_date": NOW - 10 * DAY,
        "first_submission_date": NOW - 3 * DAY,
        "times_submitted": 2,
        "last_https_certificate": {"issuer": "Let's Encrypt"},
    },
}
s_rich = extract_gti_summary(rel_item_rich)
for key in [
    "malware_families", "related_threat_actors", "associations", "campaigns",
    "sandbox_verdicts", "behaviour_summary", "crowdsourced_ids_results",
    "last_analysis_date", "creation_date", "tld", "first_seen_itw_date",
    "first_submission_date", "times_submitted", "last_https_certificate",
]:
    check(f"new field '{key}' extracted when present", key in s_rich, f"got {s_rich}")

# --- Descriptor-shaped input WITHOUT the new fields doesn't crash / doesn't fabricate them ---
rel_item_descriptor = {"id": "thin-descriptor.example", "type": "domain"}
s_thin = extract_gti_summary(rel_item_descriptor)
check("thin descriptor: no crash, returns dict", isinstance(s_thin, dict))
check("thin descriptor: only gti_id/gti_type present", set(s_thin.keys()) == {"gti_id", "gti_type"}, f"got {s_thin}")

# context_attributes shaped like a real GTI descriptor payload (non-dict, empty, etc.)
check("non-dict input does not crash", extract_gti_summary("not a dict") == {})
check("empty dict input does not crash", extract_gti_summary({}) == {})
rel_item_context = {
    "id": "ctxdomain.example",
    "type": "domain",
    "context_attributes": {"creation_date": NOW - 2 * DAY, "tld": "top"},
}
s_ctx = extract_gti_summary(rel_item_context)
check("context_attributes fields extracted when attributes absent", s_ctx.get("creation_date") == NOW - 2 * DAY and s_ctx.get("tld") == "top", f"got {s_ctx}")

print(); print("="*70)
print(f"PASSED {len(PASS)} / {len(PASS)+len(FAIL)}")
if FAIL:
    print("FAILURES:"); [print("  -", f) for f in FAIL]


def test_accuracy_fixes():
    assert not FAIL, f"failed checks: {FAIL}"
