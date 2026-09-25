from unittest.mock import Mock

import pytest
from langchain.messages import ToolMessage
from langchain_classic.docstore.document import Document


@pytest.fixture
def mock_similarity_search(mocker):
    similarity_result = [
        (Document(page_content="document 1"),0.9),
        (Document(page_content="document 2"),0.7),
        (Document(page_content="document 3"),0.5),
    ]

    mocker.patch("specialists.rag.vectorstore.similarity_search_with_score",return_value=similarity_result)
    return similarity_result

@pytest.fixture
def mock_rag_agent_low_confidence(mocker):
    fake_tool_message = ToolMessage(
        content="Retrieved context document",
        tool_call_id="call_123",
        artifact={"confidence": 0.40},
        name="search_knowledge_base"
    )

    fake_agent = Mock()
    fake_agent.invoke.return_value = {
        "messages": [fake_tool_message]
    }

    mocker.patch("specialists.rag.rag_agent", fake_agent)
    return fake_tool_message

@pytest.fixture
def mock_rag_agent_high_confidence(mocker):
    fake_tool_message = ToolMessage(
        content="Retrieved context document",
        tool_call_id="call_123",
        artifact={"confidence": 0.60},
        name="search_knowledge_base"
    )

    fake_agent = Mock()
    fake_agent.invoke.return_value = {
        "messages": [fake_tool_message]
    }

    mocker.patch("specialists.rag.rag_agent", fake_agent)
    return fake_tool_message
