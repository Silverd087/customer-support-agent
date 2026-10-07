from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from langchain.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from redis.exceptions import RedisError

from orchestrator import handle_incoming, orchestrator_graph


class TestOrchestrator:
    def test_orchestrator_calls_escalate_to_human_when_llm_requests_it(self,mocker):
        escalate_call = AIMessage(
            content="",
            tool_calls=[ToolCall({
                "name": "escalate_to_human",
                "args": {
                    "summary": "Customer reports suspicious account activity.",
                    "reason": "security_sensitive",
                    "customer_email": None,
                    "channel": "web",
                },
                "id": "call_1",
                "type": "tool_call",
            })],
        )
        final_reply = AIMessage("I've flagged this for a teammate.")
        mocker.patch("orchestrator.invoke_with_retry", side_effect=[escalate_call, final_reply])
        fake_escalation = Mock()
        fake_escalation.id = "escalation-uuid-778"
        mock_db = MagicMock()
        mock_db.scalars.return_value.one_or_none.return_value = fake_escalation

        mock_db.return_value.__enter__.return_value = mock_db
        mock_db.return_value.__exit__.return_value = False

        mocker.patch("orchestrator.get_db",mock_db)

        test_graph = orchestrator_graph.compile(checkpointer=False)
        result = test_graph.invoke({
            "messages": [HumanMessage("I think someone hacked my account")],
            "channel": "web",
        })

        mock_db.scalars.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result["messages"][-1].text == "I've flagged this for a teammate."

    def test_orchestrator_routes_to_specialist_tool_call(self,mocker,mock_rag_agent_high_confidence):
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[ToolCall({
                "name": "rag_specialist",
                "args": {"question": "What's your return policy?"},
                "id": "call_1",
                "type": "tool_call",
            })],
        )
        final_reply = AIMessage(content="Our return policy allows...")

        mocker.patch("orchestrator.invoke_with_retry", side_effect=[tool_call_msg, final_reply])

        test_graph = orchestrator_graph.compile(checkpointer=False)
        result = test_graph.invoke({
            "messages": [HumanMessage("What's your return policy?")],
            "channel": "web",
        })

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "rag_specialist"]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == mock_rag_agent_high_confidence.text
        assert result["messages"][-1].text == "Our return policy allows..."

    def test_orchestrator_ends_when_no_tool_calls(self,mocker):
        tool_call_msg = AIMessage(content="Test question")

        mocker.patch("orchestrator.invoke_with_retry", return_value=tool_call_msg)

        test_graph = orchestrator_graph.compile(checkpointer=False)
        result = test_graph.invoke({
            "messages": [HumanMessage("What's your return policy?")],
            "channel": "web",
        })        
        assert result["messages"][-1].text == "Test question"

    @pytest.mark.asyncio
    async def test_handle_incoming_rate_limited_above_threshold(self,mocker):
        mock_redis = Mock()
        mock_redis.incr.return_value = 6
        mock_ensure_ready = AsyncMock(return_value=None)

        mocker.patch("orchestrator.redis_cache",mock_redis)
        mocker.patch("orchestrator._ensure_ready",mock_ensure_ready)
        result = await handle_incoming("random query","thread123","web")
        assert result == "rate limit exceeded, wait a few minutes before making another request"

    @pytest.mark.asyncio
    async def test_handle_incoming_proceeds_when_redis_errors(self,mocker):
        final_reply = AIMessage(content="Test reply")
        mock_ensure_ready = AsyncMock(return_value=None)

        mock_redis = mocker.patch("orchestrator.redis_cache")
        mock_redis.incr.side_effect = RedisError("Connection refused")

        mocker.patch("orchestrator.invoke_with_retry", return_value=final_reply)
        mocker.patch("orchestrator._ensure_ready",mock_ensure_ready)

        test_graph = orchestrator_graph.compile(checkpointer=False)
        mocker.patch("orchestrator.orchestrator",test_graph)


        result = await handle_incoming("random query","thread123","web")

        assert result == "Test reply"

