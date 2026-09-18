
from typing import Literal, NotRequired
from uuid import UUID

from dotenv import load_dotenv
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_chroma import Chroma
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from config import settings
from logger import logger
from retries import invoke_with_retry

load_dotenv()
CRITIQUE_SYSTEM_PROMPT = """You are a fact-checker reviewing a draft customer support answer before it's sent to a customer.

You will be given:
1. RETRIEVED CONTEXT — the exact source material returned by the knowledge base search
2. DRAFT ANSWER — a draft response written based on that context

Your only job is to check whether every factual claim in the draft answer is actually supported by the retrieved context. Do not evaluate tone, style, grammar, or helpfulness — only groundedness.

Treat as unsupported: any specific price, policy detail, timeline, eligibility rule, or promise that does not appear in the retrieved context, even if it sounds plausible or matches common industry practice. If the draft says it doesn't have the information, or otherwise declines to answer, that is always APPROVED — declining to answer is never an unsupported claim.

Respond in exactly this format, nothing else:

If every claim is supported:
APPROVED

If any claim is not supported:
REVISE
<one or two sentences per unsupported claim — quote the claim, state that it has no basis in the retrieved context>

RETRIEVED CONTEXT:
{retrieved_context}

DRAFT ANSWER:
{draft_answer}
"""

llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")
embedding_model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    encode_kwargs={"normalize_embeddings": True}
)
vectorstore = Chroma(
    collection_name="organization_policies",
    persist_directory="./chroma_langchain_db",
    embedding_function=embedding_model)
tenant_id = UUID("a0000000-0000-0000-0000-000000000001")
RAG_CONFIDENCE_THRESHOLD = 0.5

class RagState(MessagesState):
    revision_count: NotRequired[int]
    critique_verdict:NotRequired[str]

class Critique(BaseModel):
    verdict:Literal["APPROVED","REVISE"] = Field(description="Binary critique decision. 'APPROVED': The context fully supports the answer and resolves the user's intent. 'REVISE': Retrieval lacks necessary facts, contains off-topic noise, or the generated answer hallucinates/misinterprets context.")
    feedback_text:str = Field(default="",description="Actionable critique and improvement suggestions. Required if critique is 'REVISE' detailing retrieval flaws or factual inaccuracies; optional or empty if 'APPROVED'.")


@tool(response_format="content_and_artifact")
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
    return {"context_chunks": [doc.page_content for doc,_ in result],"confidence":confidence}

rag_llm = llm.bind_tools([search_knowledge_base])

def rag_agent_node(state: RagState):
    return {"messages":[invoke_with_retry(rag_llm,state["messages"])]}

def critique(state:RagState):
    draft = state["messages"][-1].text
    tool_messages = [msg for msg in state["messages"] if isinstance(msg, ToolMessage)]  
    all_chunks = []
    for tm in tool_messages:
        all_chunks.extend(tm.artifact["context_chunks"])
    critique_llm = llm.with_structured_output(Critique)
    result = invoke_with_retry(critique_llm,CRITIQUE_SYSTEM_PROMPT.format(retrieved_context="\n\n".join(all_chunks),draft_answer=draft))
    verdict = result.verdict
    feedback_text = result.feedback_text
    if verdict == "APPROVED":
        logger.info("critique_verdict", verdict="approved", revision_count=state.get("revision_count",0))
        return {"critique_verdict":"APPROVED"}
    else:
        logger.info("critique_verdict", verdict="revise", revision_count=state.get("revision_count",0)+1, feedback=feedback_text)
        return {"critique_verdict":"REVISE","revision_count":state.get("revision_count",0)+1,"messages":[HumanMessage(f"[Critique feedback — revise your previous answer]: {feedback_text}")]}

def critique_condition(state:RagState):
    if isinstance(state["messages"][-1], AIMessage) and len(state["messages"][-1].tool_calls)>0:
        return "tools"
    else:
        return "critique"

def continue_agent(state:RagState):
    if state["critique_verdict"] == "APPROVED":
        return END
    elif state["critique_verdict"] == "REVISE" and state["revision_count"]<2:
        return "agent"
    else:
        return END

rag_graph = StateGraph(RagState)
rag_graph.add_node("agent",rag_agent_node)
rag_graph.add_node("tools",ToolNode([search_knowledge_base]))
rag_graph.add_node("critique",critique)
rag_graph.add_edge(START,"agent")
rag_graph.add_conditional_edges("agent",critique_condition,{"tools":"tools","critique":"critique"})
rag_graph.add_edge("tools","agent")
rag_graph.add_conditional_edges("critique",continue_agent,{END:END,"agent":"agent"})

rag_agent = rag_graph.compile()

@tool
def rag_specialist(question:str):
    """Ask the knowledge-base specialist about policies, FAQs, or troubleshooting
    steps. Always use this for anything involving a policy, price, timeline, or
    procedure — never answer those from memory."""
    result = rag_agent.invoke({"messages":[HumanMessage(question)]})
    answer =  result["messages"][-1].text

    confidence = None
    for msg in reversed(result["messages"]):
        if getattr(msg, "name", None) == "search_knowledge_base":
            confidence = msg.artifact.get("confidence") if hasattr(msg, "artifact") else None

    if confidence is not None and confidence < RAG_CONFIDENCE_THRESHOLD:
        logger.warning("rag_low_confidence", question=question, confidence=confidence)
        return f"{answer}\n\n[LOW_CONFIDENCE: retrieval score {confidence:.2f}]"
    return answer