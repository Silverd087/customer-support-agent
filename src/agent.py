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

messages = []
while True:
    message = input("\nwhat is your question? ")
    if message.lower() in ["exit","q"]:
        break
    messages.append(message)
    for event in agent.stream({"messages":messages}):
        for v in event.values():
            print(v)
    
