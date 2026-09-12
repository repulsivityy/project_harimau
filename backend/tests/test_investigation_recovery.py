"""Focused control-flow tests for new and checkpoint-resumed investigations.

The graph, persistence helper, and SSE manager are replaced with local stubs;
these tests never require Cloud SQL, a LangGraph checkpointer, or an SSE client.
"""
import asyncio

import pytest

import backend.main as main
import backend.utils.sse_manager as sse_module


class RecordingGraph:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, state, *, config):
        self.calls.append((state, config))
        return {
            "ioc": "example.test",
            "ioc_type": "domain",
            "specialist_results": {},
            "metadata": {},
            "investigation_graph": None,
        }


class RecordingSSE:
    def create_queue(self, job_id):
        pass

    async def emit_event(self, job_id, event_type, data):
        pass

    def get_events(self, job_id):
        return []

    def clear_history(self, job_id):
        pass


@pytest.fixture(autouse=True)
def clear_active_tasks():
    main.ACTIVE_TASKS.clear()
    yield
    main.ACTIVE_TASKS.clear()


def _install_background_stubs(monkeypatch):
    graph = RecordingGraph()
    saved_jobs = []

    async def save_job(job_id, data):
        saved_jobs.append((job_id, data))

    monkeypatch.setattr(main, "app_graph", graph)
    monkeypatch.setattr(main, "save_job", save_job)
    monkeypatch.setattr(sse_module, "sse_manager", RecordingSSE())
    return graph, saved_jobs


def test_new_request_persists_hunt_config_and_starts_explicit_new_run(monkeypatch):
    saved_jobs = []
    scheduled = []

    async def save_job(job_id, data):
        saved_jobs.append((job_id, data))

    async def background_worker(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr(main, "save_job", save_job)
    monkeypatch.setattr(main, "_run_investigation_background", background_worker)

    async def exercise():
        response = await main.run_investigation(
            main.InvestigationRequest(ioc=" Example.TEST ", max_iterations=4), None
        )
        await main.ACTIVE_TASKS[response["job_id"]]
        return response

    response = asyncio.run(exercise())

    persisted_job_id, persisted_job = saved_jobs[0]
    assert persisted_job_id == response["job_id"]
    assert persisted_job["status"] == "running"
    assert persisted_job["ioc"] == "example.test"
    assert persisted_job["hunt_config"] == {"max_iterations": 4}
    assert persisted_job["max_iterations"] == 4
    assert scheduled == [
        (
            (response["job_id"], "example.test", 4),
            {"resume": False, "hunt_config": {"max_iterations": 4}},
        )
    ]


def test_new_hunt_invokes_graph_with_fresh_initial_state(monkeypatch):
    graph, saved_jobs = _install_background_stubs(monkeypatch)

    asyncio.run(
        main._run_investigation_background(
            "new-job", "example.test", hunt_config={"max_iterations": 4}
        )
    )

    state, config = graph.calls[0]
    assert state["iteration"] == 0
    assert state["max_iterations"] == 4
    assert config == {"configurable": {"thread_id": "new-job"}}
    assert saved_jobs[-1][1]["hunt_config"] == {"max_iterations": 4}


def test_resumed_hunt_invokes_graph_without_replacing_checkpoint_state(monkeypatch):
    graph, saved_jobs = _install_background_stubs(monkeypatch)

    asyncio.run(
        main._run_investigation_background(
            "resume-job",
            "example.test",
            resume=True,
            hunt_config={"max_iterations": 5},
        )
    )

    assert graph.calls == [(None, {"configurable": {"thread_id": "resume-job"}})]
    assert saved_jobs[-1][1]["hunt_config"] == {"max_iterations": 5}


def test_orphaned_job_status_read_schedules_checkpoint_resume(monkeypatch):
    scheduled = []

    async def get_job(job_id):
        return {
            "job_id": job_id,
            "status": "running",
            "ioc": "example.test",
            # Existing persisted records did not have hunt_config.
            "max_iterations": 2,
        }

    async def background_worker(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr(main, "get_job", get_job)
    monkeypatch.setattr(main, "_run_investigation_background", background_worker)

    async def resumable_checkpoint(job_id):
        return True

    monkeypatch.setattr(main, "_has_resumable_checkpoint", resumable_checkpoint)

    async def exercise():
        job = await main.get_investigation("orphaned-job")
        await main.ACTIVE_TASKS["orphaned-job"]
        return job

    job = asyncio.run(exercise())

    assert job["status"] == "running"
    assert scheduled == [
        (
            ("orphaned-job", "example.test", 2),
            {"resume": True, "hunt_config": {}},
        )
    ]


def test_orphaned_job_prefers_persisted_hunt_config_for_resume(monkeypatch):
    scheduled = []

    async def get_job(job_id):
        return {
            "job_id": job_id,
            "status": "running",
            "ioc": "example.test",
            "max_iterations": 2,
            "hunt_config": {"max_iterations": 5},
        }

    async def background_worker(*args, **kwargs):
        scheduled.append((args, kwargs))

    async def resumable_checkpoint(job_id):
        return True

    monkeypatch.setattr(main, "get_job", get_job)
    monkeypatch.setattr(main, "_run_investigation_background", background_worker)
    monkeypatch.setattr(main, "_has_resumable_checkpoint", resumable_checkpoint)

    async def exercise():
        await main.get_investigation("configured-orphan")
        await main.ACTIVE_TASKS["configured-orphan"]

    asyncio.run(exercise())

    assert scheduled == [
        (
            ("configured-orphan", "example.test", 5),
            {"resume": True, "hunt_config": {"max_iterations": 5}},
        )
    ]


def test_orphaned_job_stays_running_when_checkpoint_recovery_is_unavailable(monkeypatch):
    scheduled = []

    async def get_job(job_id):
        return {"job_id": job_id, "status": "running", "ioc": "example.test"}

    async def background_worker(*args, **kwargs):
        scheduled.append((args, kwargs))

    async def unavailable_checkpoint(job_id):
        return False

    monkeypatch.setattr(main, "get_job", get_job)
    monkeypatch.setattr(main, "_run_investigation_background", background_worker)
    monkeypatch.setattr(main, "_has_resumable_checkpoint", unavailable_checkpoint)

    job = asyncio.run(main.get_investigation("unavailable-orphan"))

    assert job["status"] == "running"
    assert scheduled == []
    assert "unavailable-orphan" not in main.ACTIVE_TASKS


def test_cancellation_is_a_single_conditional_terminal_transition(monkeypatch):
    """Only the caller that changes an active DB row may publish cancellation."""
    executed = []
    events = []

    class Connection:
        async def execute(self, query, *args):
            executed.append((query, args))
            return "UPDATE 1" if len(executed) == 1 else "UPDATE 0"

    class Acquire:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return False

    class Pool:
        def acquire(self, **_kwargs):
            return Acquire()

    class SSE:
        async def emit_event(self, _job_id, event_type, data):
            events.append((event_type, data))

    monkeypatch.setattr(main, "db_pool", Pool())
    monkeypatch.setattr(sse_module, "sse_manager", SSE())

    async def exercise():
        first = await main._mark_investigation_cancelled("job-1")
        second = await main._mark_investigation_cancelled("job-1")
        return first, second

    assert asyncio.run(exercise()) == (True, False)
    assert "status IN ('running', 'pending')" in executed[0][0]
    assert [event_type for event_type, _data in events] == ["investigation_cancelled"]
