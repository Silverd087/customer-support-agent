from langchain.messages import AIMessage, ToolCall
from langgraph.graph import END, MessagesState

from specialists.rag import (
    RagState,
    continue_agent,
    critique_condition,
    rag_specialist,
    search_knowledge_base,
)


class TestRagSpecialist:
    def test_search_knowledge_base_returns_content_and_artifact_tuple(self,mock_similarity_search):
        content,artifact = search_knowledge_base.func("test_query")
        assert content is not None
        assert content == "\n\n".join(doc.page_content for doc, _ in mock_similarity_search )
        assert artifact is not None
        assert "context_chunks" in artifact
        assert "confidence" in artifact

    def test_search_knowledge_base_confidence_math(self,mock_similarity_search):
        _,artifact = search_knowledge_base.func("test_query")
        best_distance = mock_similarity_search[0][1]
        expected_confidence = 1 - (best_distance/2)
        actual_confidence = artifact["confidence"]
        assert actual_confidence == expected_confidence

    def test_critique_condition_routes_to_tools_when_tool_calls_present(self):
        ai_message = AIMessage("test ai message")
        ai_message.tool_calls = [ToolCall(
            {
            "name": "test_tool",
            "args": {"query": "test query"},
            "id": "call_123",
            "type": "tool_call",
        }
        )]
        state = MessagesState(messages=[ai_message])

        assert critique_condition(state) == "tools"

    def test_critique_condition_routes_to_critique_when_no_tool_calls(self):
        ai_message = AIMessage("test ai message")
        state = MessagesState(messages=[ai_message])

        assert critique_condition(state) == "critique"

    def test_continue_agent_ends_when_approved(self):
        state = RagState(critique_verdict="APPROVED")

        assert continue_agent(state) == END

    def test_continue_agent_loops_when_revise_under_limit(self):
        state = RagState(critique_verdict="REVISE",revision_count=1)

        assert continue_agent(state) == "agent"

    def test_continue_agent_ends_when_revise_limit_reached(self):
        state = RagState(critique_verdict="REVISE",revision_count=2)

        assert continue_agent(state) == END

    def test_rag_specialist_appends_low_confidence_flag(self,mock_rag_agent_low_confidence):
        assert "LOW_CONFIDENCE: retrieval score" in rag_specialist.func("test question")

    def test_rag_specialist_no_flag_above_threshold(self,mock_rag_agent_high_confidence):
        tool_message_text = mock_rag_agent_high_confidence.text
        assert tool_message_text == rag_specialist.func("test question")
