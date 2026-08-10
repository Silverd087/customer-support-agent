from typing import TypedDict, Annotated,List
from langgraph.graph import StateGraph,START,END, MessagesState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage
from langchain_core.messages import BaseMessage
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from config import settings
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode,tools_condition
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")
embedding_model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    encode_kwargs={"normalize_embeddings": True}
)
vectorstore = Chroma(
    collection_name="organization_policies",
    persist_directory="./chroma_langchain_db",
    embedding_function=embedding_model)



class SupportAgent(TypedDict):
    messages: Annotated[List[BaseMessage],add_messages]
    channel:str

@tool
def search_knowledge_base(query: str):
    """Searches the internal vector store for relevant documentation chunks and returns top matches with a confidence score.

    Args:
        query (str): The search query or user question to match against the vector database.

    Returns:
        dict: A dictionary containing:
            - 'context_chunks' (list[tuple[str, float]]): Up to 4 retrieved document snippets with their vector distance scores.
            - 'confidence' (float): A calculated confidence metric (0.0 to 1.0) derived from the top result's distance score.
    """
    result =  vectorstore.similarity_search_with_score(query=query,k=4)
    best_distance = result[0][1]
    confidence = 1 - (best_distance/2)
    return {"context_chunks": [(doc.page_content,score) for doc,score in result],"confidence":confidence}

rag_llm = llm.bind_tools([search_knowledge_base])

def rag_agent_node(state: MessagesState):
    return {"messages":[rag_llm.invoke(state["messages"])]}


rag_graph = StateGraph(MessagesState)
rag_graph.add_node("agent",rag_agent_node)
rag_graph.add_node("tools",ToolNode([search_knowledge_base]))
rag_graph.add_edge(START,"agent")
rag_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
rag_graph.add_edge("tools","agent")

rag_agent = rag_graph.compile()

@tool
def rag_specialist(question:str):
    """Ask the knowledge-base specialist about policies, FAQs, or troubleshooting
    steps. Always use this for anything involving a policy, price, timeline, or
    procedure — never answer those from memory."""
    result = rag_agent.invoke({"messages":question})
    return result["messages"][-1].text

specialists = [rag_specialist]
orchestrator_llm = llm.bind_tools(specialists)

def orchestrator_node(state: SupportAgent):
    return {"messages":[orchestrator_llm.invoke(state["messages"][-1])]}

orchestrator_graph = StateGraph(SupportAgent)
orchestrator_graph.add_node("agent",orchestrator_node)
orchestrator_graph.add_node("tools",ToolNode(specialists))
orchestrator_graph.add_edge(START,"agent")
orchestrator_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
orchestrator_graph.add_edge("tools","agent")

orchestrator = orchestrator_graph.compile(checkpointer=checkpointer)
messages = []
while True:
    message = input("\nwhat is your question? ")
    if message.lower() in ["exit","q"]:
        break
    messages.append(HumanMessage(message))
    result = orchestrator.invoke({"messages":messages},{"configurable": {"thread_id": "1"}})
    reply = result["messages"][-1].text
    print(reply)

    
