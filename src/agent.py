from typing import TypedDict, Annotated,List,Literal
from operator import add
from langgraph.graph import StateGraph,START,END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from pydantic import BaseModel, Field
from langchain.messages import HumanMessage,AIMessage
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from config import settings
from logger import log_query

CONFIDENCE_THRESHOLD = 0.5
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
    messages: Annotated[List[BaseMessage],add]
    channel:str
    intent: Literal["billing","technical","account","other"]
    context_chunks: List[str]
    confidence: float
    needs_human:bool

classify_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You classify incoming customer support messages for Lumen Home, a smart "
     "home device company. Assign exactly one category:\n"
     "- billing: subscriptions, charges, refunds, plan changes\n"
     "- technical: device setup, connectivity, troubleshooting, hardware faults\n"
     "- account: login, password, 2FA, account deletion, data privacy\n"
     "- other: anything that doesn't clearly fit the above (e.g. shipping, returns, general questions)\n"
     "Respond with the category only."),
    ("human", "{message}"),
])


response_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a support agent for Lumen Home (smart home devices and the Lumen+ "
     "subscription). Answer the customer's question using ONLY the context below.\n\n"
     "Rules:\n"
     "- If the answer isn't in the context, say you don't have that information and "
     "offer to connect them with a human agent. Do not guess or invent policy details, "
     "prices, timelines, or coverage terms.\n"
     "- Be concise and direct — a few sentences, not a wall of text.\n"
     "- Don't mention 'the context' or 'the documents' to the customer; just answer naturally.\n\n"
     "Context:\n{context}"),
    ("human", "{question}"),
])


class IntentClassification(BaseModel):
    intent: Literal["billing","technical","account","other"] = Field(
        description="Best-fit category for the customer's message."
    )

def classify_intent(state: SupportAgent):
    structured_llm = llm.with_structured_output(IntentClassification)

    classification = structured_llm.invoke(classify_prompt.format_messages(message=state["messages"][-1].content))
    return {"intent":classification.intent}

def retrieve_context(state: SupportAgent):
    message = state["messages"][-1].content
    result =  vectorstore.similarity_search_with_score(filter={"category":state["intent"]},query=message,k=4)
    best_distance = result[0][1]
    confidence = 1 - (best_distance/2)
    return {"context_chunks": [(doc.page_content,score) for doc,score in result],"confidence":confidence}


def generate_response(state: SupportAgent):
    chain = response_prompt | llm | StrOutputParser()
    response = chain.invoke({"context":"\n\n".join([c[0] for c in state["context_chunks"]]),"question":state["messages"][-1].content})
    log_query(
        question=state["messages"][-1].content,
        intent=state["intent"],
        chunks=state["context_chunks"],
    )
    return {"messages":[AIMessage(response)]}


def route_after_retrieve(state: SupportAgent):
    return "human_handoff" if state["confidence"]< CONFIDENCE_THRESHOLD else "generate_response"

    
graph = StateGraph(SupportAgent)
graph.add_node("classify_intent",classify_intent)
graph.add_node("retrieve_context",retrieve_context)
graph.add_node("generate_response",generate_response)
graph.add_edge(START,"classify_intent")
graph.add_edge("classify_intent","retrieve_context")
graph.add_conditional_edges("retrieve_context",route_after_retrieve,{"human_handoff":"human_handoff","generate_response":"generate_response"})
graph.add_edge("generate_response",END)

agent = graph.compile()

messages = []
while True:
    message = input("\nwhat is your question? ")
    if message.lower() in ["exit","q"]:
        break
    messages.append(HumanMessage(message))
    result = agent.invoke({"messages":messages})
    reply = result["messages"][-1].content
    print(reply)

    
