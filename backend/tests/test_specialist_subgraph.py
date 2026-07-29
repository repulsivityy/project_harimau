"""
Tests for the S4-T2 gap-closure fixes on the specialist sub-graphs:

1. tool_timeout wraps a coroutine with a wall-clock timeout (restores the
   per-tool timeout budget that run_tools_parallel used to provide before the
   ToolNode refactor).
2. run_tools_parallel is fully removed (dead code cleanup).
3. functools.wraps preservation lets @tool sit on top of @tool_timeout without
   losing __name__/__doc__ (langchain_core.tools.tool reads these to build the
   tool's .name / .description).
4. The hoisted, module-level route_after_agent / route_after_init routers in
   backend.agents.malware and backend.agents.infrastructure are hardened
   against missing/empty messages and non-AIMessage last messages.

Plain pytest, no pytest-asyncio dependency: coroutines are driven with
asyncio.run(...) inside ordinary sync test functions.
"""
import asyncio
import json

import backend.utils.agent_utils as agent_utils
from backend.utils.agent_utils import tool_timeout
from langchain_core.tools import tool

from backend.agents import malware
from backend.agents import infrastructure
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# 1. tool_timeout: fast coroutine passes its return value through unchanged
# ---------------------------------------------------------------------------

def test_tool_timeout_passthrough():
    @tool_timeout(seconds=5.0)
    async def fast(x):
        return f"result:{x}"

    result = asyncio.run(fast("abc"))
    assert result == "result:abc"


# ---------------------------------------------------------------------------
# 2. tool_timeout: slow coroutine times out and returns a JSON error string,
#    without raising.
# ---------------------------------------------------------------------------

def test_tool_timeout_times_out():
    @tool_timeout(seconds=0.05)
    async def slow():
        await asyncio.sleep(5)
        return "should never get here"

    result = asyncio.run(slow())
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "error" in parsed
    assert "slow" in parsed["error"]
    assert "timed out" in parsed["error"]


def test_tool_timeout_logs_on_timeout():
    calls = []

    class FakeLogger:
        def error(self, event, **kwargs):
            calls.append((event, kwargs))

    @tool_timeout(seconds=0.05, logger=FakeLogger())
    async def slow_logged():
        await asyncio.sleep(5)

    asyncio.run(slow_logged())
    assert len(calls) == 1
    event, kwargs = calls[0]
    assert event == "tool_timeout"
    assert kwargs.get("tool") == "slow_logged"


# ---------------------------------------------------------------------------
# 3. functools.wraps preservation: @tool_timeout keeps __name__/__doc__, and
#    @tool on top of it produces a tool with a matching .name/.description.
# ---------------------------------------------------------------------------

def test_tool_timeout_preserves_metadata():
    @tool_timeout()
    async def my_example_tool(value: str):
        """This is the docstring for my_example_tool."""
        return value

    assert my_example_tool.__name__ == "my_example_tool"
    assert my_example_tool.__doc__ == "This is the docstring for my_example_tool."


def test_tool_decorator_stacks_on_tool_timeout():
    @tool
    @tool_timeout()
    async def my_stacked_tool(value: str):
        """Docstring used as the tool description."""
        return value

    assert my_stacked_tool.name == "my_stacked_tool"
    assert my_stacked_tool.description == "Docstring used as the tool description."

    # The real risk of decorator stacking is not the name/description (those
    # survive a hand-rolled wrapper too) but the generated arg schema: if
    # inspect.signature can't see through to the wrapped function via
    # __wrapped__, @tool collapses the schema to *args/**kwargs and every tool
    # declaration sent to the model becomes unusable — silently, at runtime.
    props = my_stacked_tool.args_schema.model_json_schema()["properties"]
    assert set(props) == {"value"}
    assert props["value"]["type"] == "string"
    assert "args" not in props and "kwargs" not in props


def test_real_specialist_tool_schema_survives_stacking():
    """Guards the same property on the actual decorator pair the agents use."""
    @tool
    @tool_timeout(logger=None)
    async def get_entities_related_to_a_domain(domain: str, relationship: str):
        """Get entities related to a domain."""
        return "[]"

    schema = get_entities_related_to_a_domain.args_schema.model_json_schema()
    assert set(schema["properties"]) == {"domain", "relationship"}
    assert set(schema.get("required", [])) == {"domain", "relationship"}


# ---------------------------------------------------------------------------
# 3b. tool_timeout catch-all: a tool body raising a non-timeout exception must
#     become a normal tool result, not propagate.
#
#     ToolNode's default handle_tool_errors (_default_handle_tool_errors in
#     langgraph.prebuilt.tool_node) returns a message only for
#     ToolInvocationError and RE-RAISES everything else, which aborts the whole
#     specialist. Every tool body awaits emit_tool_call() *outside* its own
#     try/except, so an SSE failure (browser tab closed mid-hunt) reaches here.
# ---------------------------------------------------------------------------

def test_tool_timeout_catches_arbitrary_exception():
    @tool_timeout(seconds=5.0)
    async def explodes():
        raise KeyError("job-123")

    result = asyncio.run(explodes())
    parsed = json.loads(result)
    assert "explodes" in parsed["error"]
    assert "failed" in parsed["error"]


def test_tool_timeout_does_not_swallow_cancellation():
    """CancelledError is BaseException-derived; genuine cancellation must pass through."""
    @tool_timeout(seconds=5.0)
    async def cancelled():
        raise asyncio.CancelledError()

    try:
        asyncio.run(cancelled())
    except asyncio.CancelledError:
        return
    raise AssertionError("CancelledError was swallowed by tool_timeout")


def test_toolnode_survives_raising_tool():
    """
    End-to-end guard for the regression: drive a real ToolNode over a tool
    decorated with the production @tool/@tool_timeout stack whose body raises.
    Without the catch-all this raises instead of returning a ToolMessage.
    """
    import operator
    from typing import Annotated, TypedDict

    from langchain_core.messages import BaseMessage
    from langgraph.graph import StateGraph, START, END
    from langgraph.prebuilt import ToolNode

    @tool
    @tool_timeout(seconds=5.0)
    async def failing_tool(value: str):
        """A tool whose body raises a non-validation error."""
        raise RuntimeError("upstream exploded")

    class _State(TypedDict):
        messages: Annotated[list[BaseMessage], operator.add]

    # Drive it through a compiled graph rather than ToolNode.ainvoke directly,
    # so the node runs with the same runtime plumbing it gets in production.
    builder = StateGraph(_State)
    builder.add_node("tools", ToolNode([failing_tool]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()

    ai = AIMessage(
        content="",
        tool_calls=[{"name": "failing_tool", "args": {"value": "x"}, "id": "call_1"}],
    )

    result = asyncio.run(graph.ainvoke({"messages": [ai]}))

    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert len(tool_messages) == 1
    assert "upstream exploded" in tool_messages[0].content


# ---------------------------------------------------------------------------
# 4. run_tools_parallel is gone.
# ---------------------------------------------------------------------------

def test_run_tools_parallel_removed():
    assert not hasattr(agent_utils, "run_tools_parallel")


# ---------------------------------------------------------------------------
# 5. route_after_agent (malware) — routing decisions.
# ---------------------------------------------------------------------------

def _ai_message_with_tool_calls():
    return AIMessage(
        content="",
        tool_calls=[{"name": "get_file_report", "args": {"file_hash": "a" * 64}, "id": "call_1"}],
    )


def test_malware_route_after_agent_empty_messages():
    sub_state = {"messages": [], "loop_step": 0, "max_iterations": 10}
    assert malware.route_after_agent(sub_state) == "final"


def test_malware_route_after_agent_missing_messages_key():
    sub_state = {"loop_step": 0, "max_iterations": 10}
    assert malware.route_after_agent(sub_state) == "final"


def test_malware_route_after_agent_no_tool_calls_attribute():
    # A plain HumanMessage has no .tool_calls attribute at all.
    sub_state = {"messages": [HumanMessage(content="hi")], "loop_step": 0, "max_iterations": 10}
    assert malware.route_after_agent(sub_state) == "final"


def test_malware_route_after_agent_empty_tool_calls():
    sub_state = {"messages": [AIMessage(content="done", tool_calls=[])], "loop_step": 0, "max_iterations": 10}
    assert malware.route_after_agent(sub_state) == "final"


def test_malware_route_after_agent_max_iterations_reached():
    sub_state = {
        "messages": [_ai_message_with_tool_calls()],
        "loop_step": 10,
        "max_iterations": 10,
    }
    assert malware.route_after_agent(sub_state) == "final"


def test_malware_route_after_agent_routes_to_tools():
    sub_state = {
        "messages": [_ai_message_with_tool_calls()],
        "loop_step": 0,
        "max_iterations": 10,
    }
    assert malware.route_after_agent(sub_state) == "tools"


# ---------------------------------------------------------------------------
# 6. route_after_init — both malware (analysis_targets) and infrastructure
#    (unique_targets), verifying each file keeps its own state key.
# ---------------------------------------------------------------------------

def test_malware_route_after_init_end_on_empty():
    assert malware.route_after_init({"analysis_targets": []}) == "end"


def test_malware_route_after_init_end_on_missing():
    assert malware.route_after_init({}) == "end"


def test_malware_route_after_init_agent_when_targets_present():
    assert malware.route_after_init({"analysis_targets": [{"hash": "a" * 64}]}) == "agent"


def test_infra_route_after_init_end_on_empty():
    assert infrastructure.route_after_init({"unique_targets": []}) == "end"


def test_infra_route_after_init_end_on_missing():
    assert infrastructure.route_after_init({}) == "end"


def test_infra_route_after_init_agent_when_targets_present():
    assert infrastructure.route_after_init({"unique_targets": [{"value": "evil.example"}]}) == "agent"


# ---------------------------------------------------------------------------
# 7. route_after_agent (infrastructure) — same hardening as malware.
# ---------------------------------------------------------------------------

def test_infra_route_after_agent_empty_messages():
    sub_state = {"messages": [], "loop_step": 0, "max_iterations": 10}
    assert infrastructure.route_after_agent(sub_state) == "final"


def test_infra_route_after_agent_missing_messages_key():
    sub_state = {"loop_step": 0, "max_iterations": 10}
    assert infrastructure.route_after_agent(sub_state) == "final"


def test_infra_route_after_agent_no_tool_calls_attribute():
    sub_state = {"messages": [HumanMessage(content="hi")], "loop_step": 0, "max_iterations": 10}
    assert infrastructure.route_after_agent(sub_state) == "final"


def test_infra_route_after_agent_empty_tool_calls():
    sub_state = {"messages": [AIMessage(content="done", tool_calls=[])], "loop_step": 0, "max_iterations": 10}
    assert infrastructure.route_after_agent(sub_state) == "final"


def test_infra_route_after_agent_max_iterations_reached():
    sub_state = {
        "messages": [_ai_message_with_tool_calls()],
        "loop_step": 10,
        "max_iterations": 10,
    }
    assert infrastructure.route_after_agent(sub_state) == "final"


def test_infra_route_after_agent_routes_to_tools():
    sub_state = {
        "messages": [_ai_message_with_tool_calls()],
        "loop_step": 0,
        "max_iterations": 10,
    }
    assert infrastructure.route_after_agent(sub_state) == "tools"
