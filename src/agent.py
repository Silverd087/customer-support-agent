from typing import TypedDict, Annotated,List
from operator import add
from langgraph.graph import StateGraph,START,END

class SupportAgent(TypedDict):
    messages: Annotated[List[str],add]
    channel:str
    intent: str
    context_chunks: List[str]
    confidence: float
    needs_human:bool


def echo(state: SupportAgent):
    return state

graph = StateGraph(SupportAgent)
graph.add_node("echo",echo)
graph.add_edge(START,"echo")
graph.add_edge("echo",END)

agent = graph.compile()

print(agent.invoke({"messages":["hello"]}))
