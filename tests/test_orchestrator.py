import itertools
from src.agent import orchestrator
from langchain.messages import HumanMessage


_thread_ids = itertools.count()

def ask(question:str,thread_id:str | None = None):
    thread_id = thread_id or f"test-{next(_thread_ids)}"
    return orchestrator.invoke({"messages":[HumanMessage(question)]},
    {"configurable": {"thread_id": thread_id}},
)

def used_tool(result, tool_name: str) -> bool:
    return any(
        getattr(msg, "tool_calls", None) and any(tc["name"] == tool_name for tc in msg.tool_calls)
        for msg in result["messages"]
    )
def test_rag_specialist_called_for_policy_question():
    result = ask("What Wi-Fi frequency do Lumen devices need?")
    assert used_tool(result, "rag_specialist")


def test_multi_turn_memory():
    tid = "test-multiturn"
    ask("How long is the return window?", thread_id=tid)
    result = ask("What if the item arrived damaged though?", thread_id=tid)
    assert "damaged" in result["messages"][-1].content.lower() or "transit" in result["messages"][-1].content.lower()