"""Focused continuity tests for specialist evidence retained in the graph cache."""

from backend.agents.lead_hunter_planning import _format_lead_for_prompt
from backend.graph.state import merge_graphs
from backend.utils.graph_cache import InvestigationCache


def test_parallel_specialist_evidence_survives_merge_and_stays_prompt_bounded():
    """Synthetic tool/structured outputs must outlive parallel branch fan-in."""
    malware = InvestigationCache()
    malware.add_entity("c2.example", "domain", {})
    malware.record_tool_evidence(
        "malware", "get_network_activity", "c2.example",
        '{"domains": ["c2.example"], "raw": "tool-backed-c2-evidence"}',
    )
    malware_outcomes = {"malware:c2.example": {
        "agent": "malware", "target_id": "c2.example", "status": "succeeded",
        "evidence": {"behavior": "Observed callback"}, "reason": None,
    }}
    malware_attempt = {"id": "malware:0:structured", "iteration": 0}
    malware.record_target_outcomes(malware_outcomes, malware_attempt)
    malware.record_specialist_result("malware", {
        "verdict": "Malicious", "network_indicators": ["c2.example"],
        "summary": "The sample contacted the C2 domain.",
        "analyzed_targets": [{
            "indicator": "c2.example", "type": "domain", "verdict": "Malicious",
            "behavior": "Observed callback", "notes": "Sandbox network evidence",
        }],
    }, malware_outcomes, malware_attempt)

    infrastructure = InvestigationCache()
    infrastructure.add_entity("c2.example", "domain", {})
    infrastructure.record_tool_evidence(
        "infrastructure", "get_domain_report", "c2.example",
        '{"gti_assessment": {"verdict": "MALICIOUS"}}',
    )
    infrastructure_outcomes = {"infrastructure:c2.example": {
        "agent": "infrastructure", "target_id": "c2.example", "status": "succeeded",
        "evidence": {"notes": "GTI report corroboration"}, "reason": None,
    }}
    infrastructure_attempt = {"id": "infrastructure:0:structured", "iteration": 0}
    infrastructure.record_target_outcomes(infrastructure_outcomes, infrastructure_attempt)
    infrastructure.record_specialist_result("infrastructure", {
        "verdict": "Malicious", "categories": ["command-and-control"],
        "summary": "GTI corroborates malicious infrastructure.",
        "analyzed_targets": [{
            "indicator": "c2.example", "type": "domain", "verdict": "Malicious",
            "notes": "GTI report corroboration",
        }],
    }, infrastructure_outcomes, infrastructure_attempt)

    merged = InvestigationCache(merge_graphs(malware.get_state(), infrastructure.get_state()))
    node = merged.get_entity_full("c2.example")

    assert {item["agent"] for item in node["specialist_tool_evidence"]} == {"malware", "infrastructure"}
    assert {item["agent"] for item in node["specialist_findings"]} == {"malware", "infrastructure"}
    assert node["specialist_tool_evidence"][0]["output"]["raw"] == "tool-backed-c2-evidence"

    prompt_line = _format_lead_for_prompt({"id": "c2.example", **node})
    assert "specialist_evidence=" in prompt_line
    assert "Observed callback" in prompt_line
    assert "tool-backed-c2-evidence" not in prompt_line
