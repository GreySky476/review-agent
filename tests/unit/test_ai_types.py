"""Tests for AI provider types."""

from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse, AIMessage


class TestAIMessage:
    def test_create_system_message(self) -> None:
        msg = AIMessage(role="system", content="You are a code reviewer")
        assert msg.role == "system"
        assert msg.content == "You are a code reviewer"


class TestAICompletionRequest:
    def test_create_request(self) -> None:
        req = AICompletionRequest(
            model="deepseek-v4-flash",
            messages=[AIMessage(role="user", content="hello")],
        )
        assert req.model == "deepseek-v4-flash"
        assert len(req.messages) == 1
        assert req.temperature == 0.1
        assert req.max_tokens == 4096


class TestAICompletionResponse:
    def test_create_response(self) -> None:
        resp = AICompletionResponse(
            content="Hi there",
            model="deepseek-v4-flash",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
        assert resp.content == "Hi there"
        assert resp.usage is not None
        assert resp.usage["prompt_tokens"] == 10
