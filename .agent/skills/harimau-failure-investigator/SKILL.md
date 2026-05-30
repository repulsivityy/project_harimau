---
name: harimau-failure-investigator
description: Systematically investigates Harimau platform failures by reviewing logs, tracing execution flow, and applying verification tests.
---

# Harimau Failure Investigator

## Overview

Use this skill to debug failures, hangs, or empty results in the Harimau investigation pipeline. It follows a strict three-step sequence to identify, isolate, and verify fixes for issues.

## Workflow

### Step 1: Review the Logs

The first step is to gather evidence from the backend logs to identify where and why the failure occurred.

**Action:** Fetch the most recent logs from the `harimau-backend` Cloud Run service:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=harimau-backend" --limit 50
```

**Analysis Checklist:**
-   **Search for Errors**: Look for `level: error`, Python Tracebacks, or specific error events like `triage_fatal_error` or `lead_hunter_failed`.
-   **Check Model Responses**: Look for `JSONDecodeError` or `TypeError` which often indicate the LLM returned unexpected structures.
-   **Identify Job ID**: Find the `job_id` associated with the failure to trace its specific path.

### Step 2: Trace the Entire Flow

Using the logs and the job ID, reconstruct the execution path through the LangGraph workflow to find the breaking point.

**Tracing Checklist:**
1.  **Triage Phase**: Did `triage` complete? Check `triage_completed` event. Did it generate subtasks? If `state["subtasks"]` is empty here, the investigation may end prematurely.
2.  **Routing Phase**: Check `gate_node_routing` logs. Did it route to specialists or skip directly to `lead_hunter`?
3.  **Specialist Phase**: Did `malware_specialist` or `infrastructure_specialist` run? Check for tool call responses (e.g., `malware_tool_response`) and successful completion events.
4.  **Synthesis/Planning Phase**: Check `lead_hunter_start`. Did it enter planning or synthesis mode? This is a common failure point during model migrations.

### Step 3: Apply Tests and Checks

Once the failure point and cause are identified, create isolated tests to verify the fix before deploying.

**Verification Checklist:**
1.  **Create Focused Unit Test**:
    -   Create a test file in `backend/tests/` (e.g., `test_failure_case.py`).
    -   Use `unittest.IsolatedAsyncioTestCase` for async nodes.
    -   Mock the LLM response with the problematic content found in Step 1 to reproduce the error.
2.  **Run the Test**:
    -   Execute the test locally: `PYTHONPATH=. python3 -m unittest backend/tests/test_failure_case.py`
    -   Verify that the fix handles the edge case without breaking existing functionality.
3.  **Verify Results**: Ensure the test output is `OK` and no errors are logged by the internal exception handlers.
