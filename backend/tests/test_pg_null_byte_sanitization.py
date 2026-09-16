import asyncio
import json
import re
import sys
from datetime import datetime
from unittest.mock import MagicMock

# Mock external heavy dependencies so this unit test can run with any standard Python interpreter
for mod in [
    "fastapi",
    "pydantic",
    "asyncpg",
    "backend.utils.logger",
    "backend.graph.workflow",
    "backend.config",
    "backend.utils",
    "backend.utils.checkpointer_registry",
    "backend.utils.entity_identity",
    "backend.utils.sse_manager",
]:
    sys.modules.setdefault(mod, MagicMock())

# Ensure @app.get(...) / @app.post(...) / etc. return the original coroutine function unchanged
_fastapi_mock = sys.modules["fastapi"]
def _passthrough_decorator(*args, **kwargs):
    def _wrapper(fn):
        return fn
    return _wrapper
_app_instance_mock = MagicMock()
for _method in ("get", "post", "put", "delete", "patch", "options", "head", "on_event"):
    getattr(_app_instance_mock, _method).side_effect = _passthrough_decorator
_fastapi_mock.FastAPI.return_value = _app_instance_mock

import backend.main as main


class DummyPatch:
    def setattr(self, obj, attr, val):
        setattr(obj, attr, val)


def test_sanitize_pg_payload_strips_null_bytes_only():
    """Verify _sanitize_pg_payload strips real \\x00 bytes while preserving literal \\u0000 text."""
    raw = {
        "str_with_null": "cmd.exe\x00 /c calc.exe",
        "str_with_escaped_null": "memory\\u0000dump",
        "str_with_double_escaped": "valid\\\\u0000literal",
        "nested_list": ["item\x001", ("tuple\x002", "clean")],
        "nested_dict": {"k\x00ey": "val\x00ue", "keep_literal": "literal\\u0000pattern"},
    }
    cleaned = main._sanitize_pg_payload(raw)
    assert cleaned["str_with_null"] == "cmd.exe /c calc.exe"
    # Literal six-character \u0000 text is preserved so malware/evidence strings are not corrupted
    assert cleaned["str_with_escaped_null"] == "memory\\u0000dump"
    assert cleaned["str_with_double_escaped"] == "valid\\\\u0000literal"
    assert cleaned["nested_list"] == ["item1", ("tuple2", "clean")]
    assert cleaned["nested_dict"] == {"key": "value", "keep_literal": "literal\\u0000pattern"}

    dumped = json.dumps(cleaned)
    # json.dumps() escapes literal backslashes, so there should be no unescaped \u0000 sequence
    assert re.search(r'(?<!\\)(?:\\\\)*\\u0000', dumped) is None


def test_save_job_strips_null_bytes_and_fallback_prevents_orphan_loop():
    """Verify save_job strips null bytes before DB execution, and fallback UPDATE
    prevents jobs from remaining 'running' when primary INSERT fails.
    """
    monkeypatch = DummyPatch()

    # 1. Test null byte stripping in save_job
    executed = []

    class Conn:
        async def execute(self, query, *args):
            executed.append((query, args))
            return "INSERT 0 1"

    class Acquire:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *exc):
            return False

    class Pool:
        def acquire(self, timeout=None):
            return Acquire()

    monkeypatch.setattr(main, "db_pool", Pool())

    payload = {
        "status": "completed",
        "ioc": "autoupdatet.com\x00",
        "ioc_type": "domain",
        "risk_level": "High",
        "gti_score": 85,
        "final_report": "Malware string: cmd.exe\x00 /c calc.exe and raw \\u0000 byte",
        "metadata": {
            "specialist_results": {
                "malware": {"raw_memory": "MZ\x00\x00PE\x00\x00\\u0000test"}
            }
        },
        "investigation_graph": {
            "nodes": [{"id": "file1", "label": "bad\x00file.exe", "escaped": "val\\u0000here"}],
            "links": [],
        },
    }

    asyncio.run(main.save_job("job-null-test", payload))
    assert len(executed) == 1
    _query, args = executed[0]
    job_id, status, ioc, _ioc_type, _risk, _score, report, meta_json, graph_json = args
    assert job_id == "job-null-test"
    assert status == "completed"
    assert "\x00" not in ioc
    assert "\x00" not in report
    assert "\x00" not in meta_json
    assert "\x00" not in graph_json

    # 2. Test fallback UPDATE when primary INSERT fails
    executed_fallback = []

    class FailingConn:
        async def execute(self, query, *args):
            executed_fallback.append((query, args))
            if "INSERT INTO investigations" in query:
                raise RuntimeError("unsupported Unicode escape sequence")
            return "UPDATE 1"

        async def fetchrow(self, query, job_id):
            return {
                "job_id": job_id,
                "status": "running",
                "ioc": "autoupdatet.com",
                "created_at": None,
                "completed_at": None,
                "metadata": "{}",
                "investigation_graph": None,
            }

    class FailingAcquire:
        async def __aenter__(self):
            return FailingConn()

        async def __aexit__(self, *exc):
            return False

    class FailingPool:
        def acquire(self, timeout=None):
            return FailingAcquire()

    monkeypatch.setattr(main, "db_pool", FailingPool())
    main.JOBS.clear()

    fallback_payload = {
        "job_id": "job-fallback-test",
        "status": "completed",
        "ioc": "autoupdatet.com",
        "ioc_type": "domain",
        "risk_level": "High",
        "gti_score": 88,
        "final_report": "Completed report",
    }

    asyncio.run(main.save_job("job-fallback-test", fallback_payload))
    assert len(executed_fallback) == 2
    assert "INSERT INTO investigations" in executed_fallback[0][0]
    assert "UPDATE investigations" in executed_fallback[1][0]
    assert executed_fallback[1][1] == (
        "job-fallback-test",
        "completed",
        "Completed report",
        "domain",
        "High",
        88,
    )

    job = asyncio.run(main.get_job("job-fallback-test"))
    assert job["status"] == "completed"


def test_get_job_and_list_jobs_terminal_memory_state_merges_normalized_db_shape():
    """Verify get_job and list_jobs merge terminal in-memory state over normalized DB row shape,
    ensuring terminal status is adopted, UTC timestamps are populated, and unpacked top-level
    keys are retained.
    """
    monkeypatch = DummyPatch()
    main.JOBS.clear()

    class NormalizingConn:
        async def fetchrow(self, query, job_id):
            return {
                "job_id": job_id,
                "status": "running",
                "ioc": "example.com",
                "ioc_type": "domain",
                "risk_level": "High",
                "gti_score": 90,
                "final_report": "In progress report",
                # Real DB rows always have a non-null created_at (DB default).
                # Using a real datetime here exercises the .isoformat() normalisation
                # branch in get_job(), which a None value would silently skip.
                "created_at": datetime(2026, 9, 16, 6, 0, 50),
                "completed_at": None,
                "metadata": json.dumps({
                    "subtasks": [{"id": 1}],
                    "rich_intel": {"whois": "data"},
                    "specialist_results": {"dns": {"records": ["1.1.1.1"]}},
                    "transparency_log": ["started"],
                    "scheduled_entities": ["example.com"],
                    "processed_entities": ["example.com"],
                    "target_outcomes": {"example.com": "done"},
                    "has_unresolved_specialist_gaps": False,
                    "investigation_outcome": "complete",
                    "hunt_config": {"max_iterations": 3},
                    "max_iterations": 3,
                }),
                "investigation_graph": None,
            }

        async def fetch(self, query, limit):
            return [
                {
                    "job_id": "job-merge-test",
                    "ioc": "example.com",
                    "ioc_type": None,
                    "status": "running",
                    "created_at": datetime(2026, 9, 16, 6, 0, 50),
                }
            ]

    class NormalizingAcquire:
        async def __aenter__(self):
            return NormalizingConn()

        async def __aexit__(self, *exc):
            return False

    class NormalizingPool:
        def acquire(self, timeout=None):
            return NormalizingAcquire()

    monkeypatch.setattr(main, "db_pool", NormalizingPool())

    # In-memory terminal job stored by worker (raw dict without created_at / completed_at)
    main.JOBS["job-merge-test"] = {
        "job_id": "job-merge-test",
        "status": "completed",
        "ioc": "example.com",
        "ioc_type": "domain",
        "final_report": "Final completed report from memory",
    }

    result = asyncio.run(main.get_job("job-merge-test"))

    # (a) Status is equal to terminal status
    assert result["status"] == "completed"
    assert result["final_report"] == "Final completed report from memory"

    # (b) Non-None created_at and timezone-aware UTC completed_at
    assert result["created_at"] is not None
    assert result["completed_at"] is not None
    assert result["completed_at"].endswith("+00:00")

    # (c) Contains unpacked top-level keys
    assert result["subtasks"] == [{"id": 1}]
    assert result["rich_intel"] == {"whois": "data"}
    assert result["specialist_results"] == {"dns": {"records": ["1.1.1.1"]}}
    assert result["transparency_log"] == ["started"]
    assert result["scheduled_entities"] == ["example.com"]
    assert result["processed_entities"] == ["example.com"]
    assert result["target_outcomes"] == {"example.com": "done"}
    assert result["has_unresolved_specialist_gaps"] is False
    assert result["investigation_outcome"] == "complete"
    assert result["hunt_config"] == {"max_iterations": 3}
    assert result["max_iterations"] == 3

    # (d) Verify list_jobs also overlays terminal status and ioc_type from JOBS
    jobs_list = asyncio.run(main.list_jobs(limit=10))
    assert len(jobs_list) == 1
    assert jobs_list[0]["status"] == "completed"
    assert jobs_list[0]["ioc_type"] == "domain"


def test_orphan_resume_capped_at_max_attempts():
    """Verify get_investigation caps auto-resume retries at MAX_RESUME_ATTEMPTS (3)
    and transitions repeatedly failing/orphaned jobs to 'failed' status instead of looping infinitely.
    """
    monkeypatch = DummyPatch()
    monkeypatch.setattr(main, "db_pool", None)
    main.JOBS.clear()
    main.ACTIVE_TASKS.clear()
    main.RESUME_ATTEMPTS.clear()

    spawned_resumes = []

    async def fake_has_checkpoint(job_id: str) -> bool:
        return True

    async def fake_run_background(job_id, ioc, max_iters, *, resume=False, hunt_config=None):
        spawned_resumes.append((job_id, resume, max_iters))

    monkeypatch.setattr(main, "_has_resumable_checkpoint", fake_has_checkpoint)
    monkeypatch.setattr(main, "_run_investigation_background", fake_run_background)

    job_id = "job-orphan-loop"
    main.JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "ioc": "bad-domain.com",
        "metadata": {},
        "hunt_config": {"max_iterations": 2},
    }

    async def run_polls():
        # Polls 1..MAX_RESUME_ATTEMPTS should each spawn a resume task
        for expected_attempt in range(1, main.MAX_RESUME_ATTEMPTS + 1):
            res = await main.get_investigation(job_id)
            assert res["status"] == "running"
            assert res["metadata"]["resume_attempts"] == expected_attempt
            # Wait for spawned task coroutine to run, then simulate worker crash / orphan state
            task = main.ACTIVE_TASKS.get(job_id)
            assert task is not None
            await task
            main.ACTIVE_TASKS.pop(job_id, None)

        assert len(spawned_resumes) == main.MAX_RESUME_ATTEMPTS

        # Simulate a different Cloud Run instance handling the 4th poll (in-memory RESUME_ATTEMPTS empty,
        # but metadata["resume_attempts"] == 3 persisted in job record)
        main.RESUME_ATTEMPTS.clear()

        # Poll 4 (exceeds MAX_RESUME_ATTEMPTS): must mark job failed and NOT spawn another task
        res4 = await main.get_investigation(job_id)
        assert res4["status"] == "failed"
        assert "exceeded maximum checkpoint resume attempts" in res4["metadata"]["error"]
        assert "exceeded maximum checkpoint resume attempts" in res4["final_report"]
        assert len(spawned_resumes) == main.MAX_RESUME_ATTEMPTS
        assert job_id not in main.ACTIVE_TASKS
        assert job_id not in main.RESUME_ATTEMPTS

        # Poll 5: job is now terminal ('failed'), no further resume checks or tasks
        res5 = await main.get_investigation(job_id)
        assert res5["status"] == "failed"
        assert len(spawned_resumes) == main.MAX_RESUME_ATTEMPTS

    asyncio.run(run_polls())


if __name__ == "__main__":
    test_sanitize_pg_payload_strips_null_bytes_only()
    test_save_job_strips_null_bytes_and_fallback_prevents_orphan_loop()
    test_get_job_and_list_jobs_terminal_memory_state_merges_normalized_db_shape()
    test_orphan_resume_capped_at_max_attempts()
    print("ALL TESTS PASSED: Null byte sanitization, fallback, get_job/list_jobs shape normalization, and orphan resume cap verified.")
