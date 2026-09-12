"""Focused target-lifecycle tests for capped specialist dispatch.

These tests stub the cache, LLM constructor, and planning call. They exercise
only orchestration state and never contact GTI, Cloud SQL, or an LLM service.
"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from backend.agents import lead_hunter
from backend.utils.target_outcomes import (
    assess_target_outcomes,
    select_malware_target_ids,
    successful_target_ids,
)


class StubLLM:
    def __init__(self, **_kwargs):
        pass


PROCESSED_HASHES = [f"{number:x}" * 64 for number in range(1, 6)]
DEFERRED_HASH = "f" * 64


@pytest.mark.parametrize(
    ("agent", "entity_type", "processed_ids", "deferred_id"),
    [
        (
            "malware_specialist",
            "file",
            PROCESSED_HASHES,
            DEFERRED_HASH,
        ),
        (
            "infrastructure_specialist",
            "domain",
            [f"processed-{number}.example.test" for number in range(1, 11)],
            "deferred.example.test",
        ),
    ],
)
def test_lead_hunter_requeues_target_deferred_by_specialist_cap(
    monkeypatch, agent, entity_type, processed_ids, deferred_id
):
    """A deferred target outranks already processed targets in a mixed plan."""

    class TargetCache:
        def __init__(self, _graph):
            pass

        def get_uninvestigated_nodes(self):
            return [{"id": deferred_id, "entity_type": entity_type}]

    async def planned_mixed_targets(state, llm, cache, actionable):
        assert [node["id"] for node in actionable] == [deferred_id]
        return {
            "subtasks": [
                *[
                    {
                        "agent": agent,
                        "entity_id": target_id,
                        "task": "Already processed target",
                    }
                    for target_id in processed_ids
                ],
                {
                    "agent": agent,
                    "entity_id": deferred_id,
                    "task": "Analyze deferred target",
                    "context": "Deferred by the previous per-pass cap",
                }
            ],
            "investigation_complete": False,
        }

    monkeypatch.setattr(lead_hunter, "InvestigationCache", TargetCache)
    monkeypatch.setattr(lead_hunter, "ChatGoogleGenerativeAI", StubLLM)
    monkeypatch.setattr(lead_hunter, "run_planning_phase", planned_mixed_targets)

    # This represents triage scheduling six malware targets while the
    # specialist's five-target cap processed only the first five.
    state = {
        "ioc": processed_ids[0],
        "iteration": 0,
        "max_iterations": 2,
        "investigation_graph": None,
        "scheduled_entities": [*processed_ids, deferred_id],
        "tasked_entities": [*processed_ids, deferred_id],  # legacy checkpoint field
        "processed_entities": processed_ids,
        "specialist_results": {},
        "metadata": {},
    }

    result = asyncio.run(lead_hunter.lead_hunter_node(state))

    assert result["iteration"] == 1
    assert [task["entity_id"] for task in result["subtasks"]] == [deferred_id]
    assert result["scheduled_entities"] == [deferred_id]
    # The compatibility field may contain the target, but it no longer causes
    # convergence: only processed_entities is completion history.
    assert result["tasked_entities"] == [deferred_id]


def test_target_outcomes_require_target_specific_evidence_and_retry_failures(monkeypatch):
    """A final batch verdict cannot certify a target the model did not address."""
    selected = ["addressed.example.test", "omitted.example.test"]
    outcomes = assess_target_outcomes(
        selected,
        {
            "verdict": "malicious",
            "analyzed_targets": [
                {"indicator": "addressed.example.test", "verdict": "malicious", "notes": "C2 DNS evidence"}
            ],
        },
        "infrastructure",
        messages=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_domain_report",
                    "args": {"domain": "addressed.example.test"},
                    "id": "call-addressed",
                }],
            ),
            ToolMessage(content='{"data": "report"}', tool_call_id="call-addressed"),
        ],
    )

    assert successful_target_ids(outcomes) == ["addressed.example.test"]
    assert outcomes["infrastructure:omitted.example.test"]["reason"] == "not_addressed_by_model"

    class TargetCache:
        def __init__(self, _graph):
            pass

        def get_uninvestigated_nodes(self):
            return []

    async def completed_without_covering_gap(*_args):
        return {"subtasks": [], "investigation_complete": True}

    monkeypatch.setattr(lead_hunter, "InvestigationCache", TargetCache)
    monkeypatch.setattr(lead_hunter, "ChatGoogleGenerativeAI", StubLLM)
    monkeypatch.setattr(lead_hunter, "run_planning_phase", completed_without_covering_gap)

    result = asyncio.run(lead_hunter.lead_hunter_node({
        "ioc": selected[0],
        "iteration": 0,
        "max_iterations": 2,
        "investigation_graph": None,
        "processed_entities": successful_target_ids(outcomes),
        "target_outcomes": outcomes,
        "specialist_results": {},
        "metadata": {},
    }))

    assert [task["entity_id"] for task in result["subtasks"]] == ["omitted.example.test"]
    assert result["subtasks"][0]["agent"] == "infrastructure_specialist"


def test_target_outcomes_reject_placeholder_evidence_without_tool_provenance():
    """A structured placeholder cannot certify a target with no successful tool call."""
    target_id = "placeholder.example.test"
    outcomes = assess_target_outcomes(
        [target_id],
        {"analyzed_targets": [{"indicator": target_id, "verdict": "Unknown", "notes": "N/A"}]},
        "infrastructure",
    )

    assert successful_target_ids(outcomes) == []
    assert outcomes[f"infrastructure:{target_id}"]["reason"] == "missing_successful_tool_provenance"


def test_unresolved_retries_are_first_and_reserve_the_malware_cap(monkeypatch):
    """A full planner batch cannot starve a retry or duplicate it via an alias."""
    retry_id = "a" * 64
    planned_ids = [character * 64 for character in "bcdef"]

    class TargetCache:
        def __init__(self, _graph):
            pass

        def get_uninvestigated_nodes(self):
            return []

    async def planned_full_cap(*_args):
        return {
            "subtasks": [
                {"agent": "malware", "entity_id": retry_id, "task": "stale duplicate"},
                *[
                    {"agent": "malware_specialist", "entity_id": target_id, "task": "new lead"}
                    for target_id in planned_ids
                ],
            ],
            "investigation_complete": False,
        }

    monkeypatch.setattr(lead_hunter, "InvestigationCache", TargetCache)
    monkeypatch.setattr(lead_hunter, "ChatGoogleGenerativeAI", StubLLM)
    monkeypatch.setattr(lead_hunter, "run_planning_phase", planned_full_cap)

    result = asyncio.run(lead_hunter.lead_hunter_node({
        "ioc": "not-a-file",
        "iteration": 0,
        "max_iterations": 2,
        "investigation_graph": None,
        "processed_entities": [],
        "target_outcomes": {
            f"malware:{retry_id}": {
                "agent": "malware", "target_id": retry_id,
                "status": "failed", "reason": "tool_error",
            }
        },
        "specialist_results": {},
        "metadata": {},
    }))

    assert [task["entity_id"] for task in result["subtasks"]] == [retry_id, *planned_ids]
    assert result["subtasks"][0]["priority"] == "retry"
    assert select_malware_target_ids("not-a-file", result["subtasks"], []) == [retry_id, *planned_ids[:4]]
