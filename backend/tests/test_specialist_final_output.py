import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
except ImportError:
    fake_lc_core = types.ModuleType("langchain_core")
    fake_lc_messages = types.ModuleType("langchain_core.messages")

    class BaseMessage:
        def __init__(self, content="", tool_calls=None, **kwargs):
            self.content = content
            self.tool_calls = tool_calls or []
            self.additional_kwargs = kwargs.get("additional_kwargs", {})
            self.id = kwargs.get("id")

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

from backend.utils.agent_utils import resolve_specialist_structured_output


class _SchemaStub:
    REQUIRED_FIELDS = ("verdict", "threat_score", "summary")

    def __init__(self, **kwargs):
        for field in self.REQUIRED_FIELDS:
            if field not in kwargs:
                raise ValueError(f"Missing required field: {field}")
        if not isinstance(kwargs["threat_score"], int):
            raise TypeError("threat_score must be int")
        self._data = dict(kwargs)

    def model_dump(self) -> dict:
        return dict(self._data)


class _InfrastructureSpecialistOutputStub(_SchemaStub):
    pass


class _MalwareSpecialistOutputStub(_SchemaStub):
    pass


class TestSpecialistFinalOutput(unittest.IsolatedAsyncioTestCase):
    """Regression tests for `400 INVALID_ARGUMENT: Requests ending with a model turn are not supported.`"""

    async def test_direct_parse_from_ai_message_skips_redundant_llm_call(self):
        """When agent_node emits valid schema JSON in AIMessage, parse directly without calling structured_llm."""
        base_llm = MagicMock()
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(
            side_effect=AssertionError("structured_llm.ainvoke should not be called when AIMessage already has valid JSON")
        )
        base_llm.with_structured_output.return_value = structured_llm

        payload = {
            "verdict": "Malicious",
            "threat_score": 75,
            "categories": ["Malware", "Command and Control"],
            "analyzed_targets": [
                {
                    "indicator": "downloadstep.com",
                    "type": "Domain",
                    "registrar": "NameCheap",
                    "hosting_provider": "Cloudflare",
                    "whois_summary": "Registered recently",
                    "dns_resolutions": ["172.234.24.211"],
                    "ssl_certificate": "Let's Encrypt",
                }
            ],
            "pivot_findings": ["Shared IP 172.234.24.211"],
            "related_indicators": ["IP: 172.234.24.211"],
            "associated_campaigns": ["FakeCaptcha"],
            "summary": "Malicious distribution domain.",
        }

        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Investigate downloadstep.com"),
            AIMessage(
                content=[
                    {"type": "thinking", "thinking": "Checking {internal} notes first..."},
                    {"type": "text", "text": f"```json\n{json.dumps(payload, indent=2)}\n```"},
                ]
            ),
        ]

        result = await resolve_specialist_structured_output(
            base_llm, _InfrastructureSpecialistOutputStub, messages
        )
        self.assertEqual(result["verdict"], "Malicious")
        self.assertEqual(result["threat_score"], 75)
        self.assertEqual(result["analyzed_targets"][0]["indicator"], "downloadstep.com")
        base_llm.with_structured_output.assert_not_called()

    async def test_fallback_appends_human_message_so_request_never_ends_with_model_turn(self):
        """When AIMessage contains prose instead of JSON, fallback must end with a HumanMessage."""
        valid_output = _MalwareSpecialistOutputStub(
            verdict="Malicious",
            threat_score=100,
            family="FakeCaptcha / LummaStealer",
            classification="Loader",
            sophistication="Moderate",
            intent="Credential harvesting",
            summary="LummaStealer loader chain.",
        )

        async def strict_gemini_ainvoke(msgs):
            if not msgs or getattr(msgs[-1], "type", None) == "ai":
                raise RuntimeError(
                    "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Requests ending with a model turn are not supported.'}}"
                )
            return {"parsed": valid_output, "raw": AIMessage(content=""), "parsing_error": None}

        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=strict_gemini_ainvoke)
        base_llm = MagicMock()
        base_llm.with_structured_output.return_value = structured_llm

        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Analyze hash c3b8c215..."),
            AIMessage(content="I have completed the investigation. The sample is LummaStealer."),
        ]

        result = await resolve_specialist_structured_output(
            base_llm, _MalwareSpecialistOutputStub, messages
        )
        self.assertEqual(result["verdict"], "Malicious")
        self.assertEqual(result["family"], "FakeCaptcha / LummaStealer")
        structured_llm.ainvoke.assert_awaited_once()
        sent_messages = structured_llm.ainvoke.call_args[0][0]
        self.assertEqual(getattr(sent_messages[-1], "type", None), "human")

    async def test_dangling_tool_call_ai_message_is_stripped_on_max_iterations(self):
        """When max_iterations is reached and AIMessage still has tool_calls, strip it and end with HumanMessage."""
        valid_output = _InfrastructureSpecialistOutputStub(
            verdict="Suspicious",
            threat_score=60,
            summary="Partial analysis before cap.",
        )

        async def strict_gemini_ainvoke(msgs):
            if not msgs or getattr(msgs[-1], "type", None) != "human":
                raise RuntimeError("Last message must be a HumanMessage")
            for m in msgs:
                if getattr(m, "tool_calls", None):
                    raise RuntimeError("Dangling tool_calls found in message history")
            return {"parsed": valid_output, "raw": AIMessage(content=""), "parsing_error": None}

        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=strict_gemini_ainvoke)
        base_llm = MagicMock()
        base_llm.with_structured_output.return_value = structured_llm

        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Investigate target"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_domain_report", "args": {"domain": "example.com"}, "id": "call_1"}],
            ),
        ]

        result = await resolve_specialist_structured_output(
            base_llm, _InfrastructureSpecialistOutputStub, messages
        )
        self.assertEqual(result["verdict"], "Suspicious")
        structured_llm.ainvoke.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
