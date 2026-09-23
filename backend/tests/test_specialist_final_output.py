import sys
import types
import unittest

try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
except ImportError:
    fake_lc_core = types.ModuleType("langchain_core")
    fake_lc_messages = types.ModuleType("langchain_core.messages")

    class BaseMessage:
        def __init__(self, content="", tool_calls=None, **kwargs):
            self.content = content
            self.tool_calls = tool_calls or []

    class SystemMessage(BaseMessage):
        type = "system"

    class HumanMessage(BaseMessage):
        type = "human"

    class AIMessage(BaseMessage):
        type = "ai"

    fake_lc_messages.BaseMessage = BaseMessage
    fake_lc_messages.SystemMessage = SystemMessage
    fake_lc_messages.HumanMessage = HumanMessage
    fake_lc_messages.AIMessage = AIMessage
    sys.modules.setdefault("langchain_core", fake_lc_core)
    sys.modules.setdefault("langchain_core.messages", fake_lc_messages)

from backend.utils.agent_utils import ensure_trailing_human_message


class TestSpecialistFinalOutput(unittest.TestCase):
    """Regression tests for `400 INVALID_ARGUMENT: Requests ending with a model turn are not supported.`"""

    def test_appends_human_message_when_ending_with_ai_message(self):
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Investigate target"),
            AIMessage(content='{"verdict": "Malicious", "threat_score": 75}'),
        ]
        normalized = ensure_trailing_human_message(messages)
        self.assertEqual(len(normalized), 4)
        self.assertEqual(getattr(normalized[-1], "type", None), "human")

    def test_strips_dangling_tool_call_ai_message_and_ends_with_human_message(self):
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Investigate target"),
            AIMessage(content="", tool_calls=[{"name": "get_domain_report", "args": {}, "id": "1"}]),
        ]
        normalized = ensure_trailing_human_message(messages)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(getattr(normalized[-1], "type", None), "human")
        self.assertTrue(all(not getattr(m, "tool_calls", None) for m in normalized))


if __name__ == "__main__":
    unittest.main()
