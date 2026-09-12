"""Mocked regressions for coverage-unknown investigation outcomes.

These deliberately exercise contracts only: no GTI, model, database, SSE, or
application startup is invoked.
"""
import asyncio

from backend.agents import lead_hunter, triage
from backend.agents.lead_hunter_synthesis import generate_final_report_outcome
from backend.graph.sse_wrappers import with_sse_events
from backend.tools import gti


class StubLLM:
    def __init__(self, **_kwargs):
        pass


def test_direct_gti_missing_key_is_failed_not_empty(monkeypatch):
    """A configuration/API failure must not be indistinguishable from no IOC."""
    monkeypatch.delenv("GTI_API_KEY", raising=False)

    response = asyncio.run(gti._make_request("files/" + "a" * 64))

    assert response["_outcome"]["status"] == "failed"
    assert response["error"]


def test_triage_preserves_failed_enrichment_as_terminal_outcome(monkeypatch):
    """Triage stops before LLM analysis when its root enrichment failed."""
    async def failed_report(*_args, **_kwargs):
        return {
            "error": "upstream unavailable",
            "_outcome": {"status": "failed", "source": "gti", "error": "upstream unavailable"},
        }

    monkeypatch.setattr(triage.gti, "get_file_report", failed_report)
    state = {"ioc": "a" * 64, "metadata": {}, "subtasks": []}

    result = asyncio.run(triage.triage_node(state))

    assert result["metadata"]["investigation_outcome"] == {
        "status": "failed",
        "stage": "triage_enrichment",
        "error": "upstream unavailable",
        "source": "gti",
    }
    assert result["subtasks"] == []
    assert result["final_report"].startswith("# Investigation Failed")


def test_triage_rejects_failed_required_relationship_enrichment(monkeypatch):
    """A partial super-bundle may not be narrated as complete relationship coverage."""
    async def partial_report(*_args, **_kwargs):
        return {
            "data": {
                "id": "a" * 64,
                "attributes": {},
                "relationships": {},
                "_relationship_outcomes": {
                    "contacted_ips": {
                        "status": "failed",
                        "source": "gti",
                        "error": "relationship descriptors lacked a related link",
                    }
                },
            },
            "_outcome": {"status": "succeeded", "source": "gti"},
        }

    monkeypatch.setattr(triage.gti, "get_file_report", partial_report)
    result = asyncio.run(triage.triage_node({"ioc": "a" * 64, "metadata": {}, "subtasks": []}))

    assert result["investigation_outcome"]["status"] == "failed"
    assert result["investigation_outcome"]["stage"] == "triage_relationship_enrichment"
    assert "contacted_ips" in result["investigation_outcome"]["error"]


def test_planning_exception_cannot_converge_into_synthesis(monkeypatch):
    """A planner exception returns a failed terminal outcome, not an empty plan."""
    class TargetCache:
        def __init__(self, _graph):
            pass

        def get_uninvestigated_nodes(self):
            return [{"id": "pivot.example.test", "entity_type": "domain"}]

    async def failed_plan(*_args, **_kwargs):
        return {
            "subtasks": [],
            "outcome": {"status": "failed", "stage": "planning", "error": "model timeout"},
        }

    monkeypatch.setattr(lead_hunter, "InvestigationCache", TargetCache)
    monkeypatch.setattr(lead_hunter, "ChatGoogleGenerativeAI", StubLLM)
    monkeypatch.setattr(lead_hunter, "run_planning_phase", failed_plan)

    result = asyncio.run(lead_hunter.lead_hunter_node({
        "ioc": "root.example.test",
        "iteration": 0,
        "max_iterations": 2,
        "investigation_graph": None,
        "metadata": {},
        "specialist_results": {},
    }))

    assert result["investigation_outcome"]["status"] == "failed"
    assert result["investigation_outcome"]["stage"] == "planning"
    assert result["subtasks"] == []


def test_synthesis_exception_has_explicit_failed_outcome():
    """The legacy fallback report stays readable but can no longer mean success."""
    class FailingLLM:
        async def ainvoke(self, _messages):
            raise RuntimeError("provider unavailable")

    outcome = asyncio.run(generate_final_report_outcome(
        {"ioc": "root.example.test", "metadata": {}, "specialist_results": {}},
        FailingLLM(),
    ))

    assert outcome["status"] == "failed"
    assert outcome["stage"] == "synthesis"
    assert outcome["error"] == "provider unavailable"
    assert outcome["report"].startswith("# Investigation Failed")


def test_blank_synthesis_report_is_failed_outcome():
    """Whitespace from a provider is not a usable final report."""
    class BlankLLM:
        async def ainvoke(self, _messages):
            return type("Response", (), {"content": "   "})()

    outcome = asyncio.run(generate_final_report_outcome(
        {"ioc": "root.example.test", "metadata": {}, "specialist_results": {}}, BlankLLM()
    ))

    assert outcome["status"] == "failed"
    assert outcome["error"] == "synthesis returned a blank report"


def test_sse_wrapper_emits_failed_for_semantic_terminal_failure(monkeypatch):
    """A returned failure contract must not generate a misleading *_completed event."""
    events = []

    async def capture(_job_id, event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr("backend.graph.sse_wrappers.sse_manager.emit_event", capture)

    @with_sse_events("triage")
    async def failed_node(_state):
        return {
            "investigation_outcome": {"status": "failed", "stage": "triage", "error": "upstream unavailable"}
        }

    result = asyncio.run(failed_node({"job_id": "job-1", "iteration": 0, "max_iterations": 1, "subtasks": []}))

    assert result["investigation_outcome"]["status"] == "failed"
    assert [event_type for event_type, _data in events] == ["triage_started", "triage_failed"]
