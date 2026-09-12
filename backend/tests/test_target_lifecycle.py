"""Focused target-lifecycle tests for capped specialist dispatch.

These tests stub the cache, LLM constructor, and planning call. They exercise
only orchestration state and never contact GTI, Cloud SQL, or an LLM service.
"""
import asyncio

import pytest

from backend.agents import lead_hunter


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
