from typing import TypedDict, Annotated,List,Literal
from langgraph.graph import StateGraph,START,END, MessagesState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage,ToolMessage
from langchain_core.messages import BaseMessage
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from config import settings
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode,tools_condition
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine,select,and_
from database.models.order import Order
from database.models.customer import Customer
from database.models.pending_refund import PendingRefund
from database.models.subscription import Subscription
from database.models.warranty_claim import WarrantyClaim
from database.models.order_item import OrderItem
from database.models.order_return import OrderReturn
from database.models.product import Product
from database.models.tenant import Tenant
from database.models.payment import Payment
from database.models.escalation import Escalation
from uuid import UUID,uuid4
from google.auth.transport.requests import Request
from langchain_mcp_adapters.client import MultiServerMCPClient
from google.oauth2.credentials import Credentials
from database.models.pending_email_send import PendingEmailSend
import asyncio
from typing import Optional
from database.session import get_db
from pydantic import BaseModel,Field

ORCHESTRATOR_SYSTEM_PROMPT = """
You are Lumen Home's customer support assistant. You have four tools available:

- rag_specialist: for anything involving policy, pricing, timelines, troubleshooting steps,
  or procedures. Never answer these from memory — always check with rag_specialist first.
- db_specialist: for anything requiring real account data — order status, subscription
  status, warranty claims, returns, or submitting a refund/return request. Never guess at
  order or account information; always verify through db_specialist.
- gmail_specialist: for anything involving email correspondence with the customer —
  finding or reading a previous email thread, or drafting a reply to send by email. It can
  search and read Gmail threads/messages and create draft replies, but it can never send
  anything: every draft it creates is only ever queued for a human to review and send
  separately. Never tell the customer an email has been sent — only that a reply has been
  drafted and is pending review, and never promise a specific send time you can't guarantee.
- escalate_to_human: for handing off to a human teammate. See triggers below.

A single request may need more than one tool. For example, a refund request needs both a
policy check (is this covered?) and an order lookup (does this order/customer combination
exist?) before you can act — call both, in whichever order makes sense, before responding.

Escalate to a human whenever ANY of the following is true, regardless of exact phrasing:

1. The customer explicitly asks for a human, a person, a manager, or says the bot/AI isn't
   helping. This includes indirect phrasings like "can I talk to someone" or "this isn't
   working, I need real help" — not just the literal words "human" or "agent".
   -> call escalate_to_human with reason="customer_requested"

2. rag_specialist reports low or no confidence in its answer, or says it doesn't have
   relevant information. Do not guess, soften, or approximate an answer in this case — a
   confident-sounding wrong answer is worse than admitting you don't know.
   -> call escalate_to_human with reason="low_confidence"

3. The request involves account security, safety, suspected fraud, unauthorized access, or
   anything where getting it wrong could harm the customer (e.g. "someone else is using my
   account", "I think I was scammed", a request that seems designed to extract another
   customer's data).
   -> call escalate_to_human with reason="security_sensitive"

When you call escalate_to_human, write a concise summary of the situation in your own
words — what the customer wants and any relevant context (order numbers, account email,
what's already been checked) — so a human picking this up doesn't have to re-read the
whole conversation. After escalating, tell the customer plainly that you've flagged this
for a teammate; do not promise a specific response time you can't guarantee.

Never fabricate order statuses, policy details, refund amounts, or account information.
If a tool doesn't return what you need, say so honestly or escalate — don't fill the gap
with a plausible-sounding guess.
"""
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

thread_id = uuid4()
RAG_CONFIDENCE_THRESHOLD = 0.5
ALLOWED_TOOLS = ["search_threads","get_thread","get_message"]
tenant_id = UUID("a0000000-0000-0000-0000-000000000001")
llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")
embedding_model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    encode_kwargs={"normalize_embeddings": True}
)
vectorstore = Chroma(
    collection_name="organization_policies",
    persist_directory="./chroma_langchain_db",
    embedding_function=embedding_model)

write_url = f"postgresql+psycopg2://{settings.write_role_user}:{settings.write_role_password}@localhost/lumen_support"
write_engine = create_engine(url=write_url)

read_url = f"postgresql+psycopg2://{settings.read_role_user}:{settings.read_role_password}@localhost/lumen_support"
read_engine = create_engine(url=read_url)

checkpointer = PostgresSaver.fromConnString(f"postgresql://settings.db_user:settings.db_password@localhost:5432/lumen_support")
asyncio.run(checkpointer.setup())

class RagState(MessagesState):
    revision_count: int
    critique_verdict:str
class SupportAgent(TypedDict):
    messages: Annotated[List[BaseMessage],add_messages]
    channel:str

class Critique(BaseModel):
    verdict:Literal["APPROVED","REVISE"] = Field(description="Binary critique decision. 'APPROVED': The context fully supports the answer and resolves the user's intent. 'REVISE': Retrieval lacks necessary facts, contains off-topic noise, or the generated answer hallucinates/misinterprets context.")
    feedback_text:str = Field(default=None,description="Actionable critique and improvement suggestions. Required if critique is 'REVISE' detailing retrieval flaws or factual inaccuracies; optional or empty if 'APPROVED'.")

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
    return {"context_chunks": [doc.page_content for doc,_ in result],"confidence":confidence}

rag_llm = llm.bind_tools([search_knowledge_base])

def rag_agent_node(state: RagState):
    return {"messages":[rag_llm.invoke(state["messages"])]}

def critique(state:RagState):
    draft = state["messages"][-1].text
    tool_messages = [msg for msg in state["messages"] if isinstance(msg, ToolMessage)]  
    all_chunks = []
    for tm in tool_messages:
        all_chunks.extend(tm.content["context_chunks"])
    critique_llm = llm.with_structured_output(Critique)
    result = critique_llm.invoke(CRITIQUE_SYSTEM_PROMPT.format(retrieved_context="\n\n".join(all_chunks),draft_answer=draft))
    verdict = result.verdict
    feedback_text = result.feedback_text
    if verdict == "APPROVED":
        return {"critique_verdict":"APPROVED"}
    else:
        return {"critique_verdict":"REVISE","revision_count":state.get("revision_count",0)+1,"messages":[HumanMessage(f"[Critique feedback — revise your previous answer]: {feedback_text}")]}
    
def critique_condition(state:RagState):
    if len(state["messages"][-1].tool_calls)>0:
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
            confidence = msg.content.get("confidence") if hasattr(msg, "content") else None

    if confidence is not None and confidence < RAG_CONFIDENCE_THRESHOLD:
        return f"{answer}\n\n[LOW_CONFIDENCE: retrieval score {confidence:.2f}]"
    return answer


@tool
def get_order_status(order_number: str, customer_email: str)->str:
    """
    Retrieve the current status of an order for a specific customer.

    Args:
        order_number: The unique identifier of the order (UUID or string ID).
        customer_email: The email address associated with the customer account.

    Returns:
        str: The status of the order (e.g., 'active', 'shipped', 'delivered'),
             or a message indicating the order was not found.
    """
    try:
        with get_db(read_engine) as db:
            stmt = select(Order.status).join(Order.customer).where(and_(Order.number == order_number,Customer.email == customer_email))
            status = db.scalar(stmt)
            if status is None:
                return "Order not found or email does not match."
            return status.value if hasattr(status, "value") else str(status)
    except Exception as e:
        return f"Failed to fetch order: {str(e)}"

@tool
def create_refund_request(order_number: str, customer_email: str, reason: str) -> str:
    """
    Submit a pending refund request for a customer's order.

    Args:
        order_number: The unique identifier of the order to be refunded.
        customer_email: The email address associated with the order/customer.
        reason: The customer's explanation or reason for requesting a refund.

    Returns:
        str: A confirmation message containing the refund reference ID,
             or an error message if the creation failed.
    """
    try:
        with get_db(write_engine) as db:
            stmt = select(Order).join(Order.customer).where(and_(Order.number == order_number,Customer.email == customer_email))
            order = db.execute(stmt).scalar_one_or_none()
            if not order:
                return "Order not found or email does not match."
            refund = PendingRefund(order_id=order.id,customer_email=customer_email,reason=reason,tenant_id=tenant_id)
            db.add(refund)
            db.commit()
            db.refresh(refund)

            refund_id = refund.id
            ref_info = f" (Refund ID: {refund_id})" if refund_id else ""

            return f"Refund request successfully submitted{ref_info} for order '{order_number}'."
    except Exception as e:
        return f"Failed to submit refund request: {str(e)}"

@tool
def get_subscription_status(customer_email:str)->str:
    """
    Retrieve the current status of a subscription for a specific customer.

    Args:
        customer_email: The email address associated with the customer account.

    Returns:
        str: The status of the subscription (e.g., 'active', 'cancelled', 'past_due'),
             or a message indicating the subscription was not found.
    """
    try:
        with get_db(read_engine) as db:
            stmt = select(Subscription).join(Subscription.customer).where(Customer.email == customer_email).order_by(Subscription.current_period_start.desc())
            subs = db.scalars(stmt).all()
            if subs == []:
                return "Subscription not found or email does not match."
            lines = [
                f"{sub.plan.value} plan ({sub.billing_cycle.value}): {sub.status.value}, "
                f"period {sub.current_period_start} to {sub.current_period_end}"
                for sub in subs
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch subscription: {str(e)}"


@tool
def get_warranty_claim_status(order_number:str,customer_email:str)->str:
    """
    Retrieve the current status of a warranty claim for a specific customer.

    Args:
        customer_email: The email address associated with the customer account.
        order_number: The unique identifier of the order.


    Returns:
        str: The status of the warranty claim (e.g., 'submitted', 'approved', 'replacement_shipped', 'closed'),
             or a message indicating the warranty claim was not found.
    """
    try:
        with get_db(read_engine) as db:
            stmt = select(WarrantyClaim).select_from(Order).join(Order.order_items).join(Order.customer).join(OrderItem.warranty_claims).where(and_(Customer.email == customer_email,Order.number==order_number)).order_by(WarrantyClaim.created_at.desc())
            claims = db.scalars(stmt).all()
            if claims == []:
                return "warranty claim not found or email does not match."
            lines = [
                f"{claim.order_item.product.name}: {claim.status.value} "
                f"(filed {claim.created_at.date()}) — \"{claim.issue_description}\""
                for claim in claims
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch warranty claim: {str(e)}"
@tool
def get_return_status(order_number:str,customer_email:str)->str:
    """
    Retrieve the current status of a order return for a specific customer.

    Args:
        customer_email: The email address associated with the customer account.
        order_number: The unique identifier of the order.

    Returns:
        str: The status of the return (e.g., 'requested', 'label_generated', 'received', 'refunded'),
             or a message indicating the return was not found.
    """
    try:
        with get_db(read_engine) as db:
            stmt = select(OrderReturn).select_from(Order).join(Order.order_items).join(Order.customer).join(OrderItem.order_returns).where(and_(Customer.email == customer_email,Order.number==order_number)).order_by(OrderReturn.requested_at.desc())
            returns = db.scalars(stmt).all()
            if returns == []:
                return "order return not found or email does not match."
            lines = [
                f"{r.order_item.product.name}: {r.status.value} "
                f"(filed {r.requested_at.date()}) — \"{r.reason}\""
                for r in returns
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch order return: {str(e)}"
@tool
def create_return_request(order_number, customer_email, product_name,reason):
    """
    Submit a order return request for a customer's order.

    Args:
        order_number: The unique identifier of the order to be returned.
        customer_email: The email address associated with the order/customer.
        reason: The customer's explanation or reason for requesting a return.

    Returns:
        str: A confirmation message containing the order return reference ID,
             or an error message if the creation failed.
    """
    try:
        with get_db(write_engine) as db:
            stmt = select(OrderItem).join(OrderItem.order).join(Order.customer).join(OrderItem.product).where(and_(Order.number == order_number,Customer.email == customer_email,Product.name == product_name))
            order_item = db.execute(stmt).scalar_one_or_none()
            if not order_item:
                return "Order item not found or email does not match."
            order_return = OrderReturn(order_item_id=order_item.id,reason=reason,tenant_id=UUID("a0000000-0000-0000-0000-000000000001"))
            db.add(order_return)
            db.commit()
            db.refresh(order_return)

            return_id = order_return.id

            return f"Return request successfully submitted for product {product_name} for order '{order_number}' return id {return_id}."
    except Exception as e:
        return f"Failed to submit order return request: {str(e)}"

db_tools = [get_order_status,create_refund_request,get_subscription_status,get_warranty_claim_status,get_return_status,create_return_request]
db_llm = llm.bind_tools(db_tools)
def db_agent_node(state: MessagesState):
    return {"messages":[db_llm.invoke(state["messages"])]}

db_graph = StateGraph(MessagesState)
db_graph.add_node("agent",db_agent_node)
db_graph.add_node("tools",ToolNode(db_tools))
db_graph.add_edge(START,"agent")
db_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
db_graph.add_edge("tools","agent")

db_agent = db_graph.compile()

@tool
def db_specialist(query:str):
    """Delegate database-related customer support tasks to a dedicated database specialist agent.

    This specialist interacts with the database to look up real-time statuses
    and submit requests for orders, refunds, subscriptions, warranty claims,
    and returns.

    Capabilities:
        - Check order status (`get_order_status`)
        - Look up subscription details/status (`get_subscription_status`)
        - Check warranty claim progress (`get_warranty_claim_status`)
        - Check product return status (`get_return_status`)
        - Submit new refund requests (`create_refund_request`)
        - Submit new return requests (`create_return_request`)

    Args:
        query: A detailed natural language query or instruction containing all
          necessary context (e.g., customer email, order ID, return reason).

    Returns:
        str: The final response from the specialist summarizing the action taken
             or the data retrieved from the database.
    """
    result = db_agent.invoke({"messages":[HumanMessage(query)]})
    return result["messages"][-1].text


@tool
def escalate_to_human(summary, reason,customer_email,channel) -> str:
    """
    Escalate the current conversation to a human support agent.

    Use this when the customer explicitly asks for a human, when the RAG
    specialist reports low or no confidence in its answer, or when the
    request involves account security, safety, or suspected fraud.

    Args:
        summary: A concise summary, in your own words, of what the customer
            wants and any relevant context (order numbers, what's already
            been checked) — written for a human picking this up cold.
        reason: Why this is being escalated. Must be one of:
            'customer_requested', 'low_confidence', 'security_sensitive'.
        customer_email: The customer's email if known, otherwise None.
        channel: The channel this conversation is happening on. Must be
            one of: 'web', 'whatsapp', 'email', 'voice'.

    Returns:
        str: A confirmation message with the escalation reference id,
             or an error message if the escalation could not be logged.
    """
    try:
        with get_db(write_engine) as db:
            escalation = Escalation(reason=reason,summary=summary,customer_email=customer_email,channel=channel,tenant_id=tenant_id,thread_id=thread_id)
            db.add(escalation)
            db.commit()
            db.refresh(escalation)

            escalation_id = escalation.id

            return f"Escalation request successfully submitted escalation id {escalation_id}"
    except Exception as e:
        return f"Failed to escalate request to human agent: {str(e)}"



def get_gmail_headers():
    creds = Credentials.from_authorized_user_file("gmail_token.json")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("gmail_token.json", "w") as f:
            f.write(creds.to_json())
    return {"Authorization": f"Bearer {creds.token}"}

mcp_client = MultiServerMCPClient({
    "gmail": {
        "transport": "streamable_http",
        "url": "https://gmailmcp.googleapis.com/mcp/v1",
        "headers": get_gmail_headers(),
    }
})

all_gmail_tools =  asyncio.run(mcp_client.get_tools())
all_gmail_tools_by_name = {tool.name: tool for tool in all_gmail_tools}
@tool
def create_draft(customer_email:str,subject:str,body:str,replyToMessageId:Optional[str]=None):
    """
    Create a draft reply email to a customer and queue it for human approval.

    This never sends anything. It creates a Gmail draft via the Gmail MCP
    connection and logs a 'pending_review' row for a human to review and
    send later — the send step happens outside this conversation entirely.

    Args:
        customer_email: The recipient's email address.
        subject: The subject line for the draft.
        body: The plain-text body of the draft.
        replyToMessageId: The id of the message being replied to, if this
            draft is a reply within an existing thread (get it from
            search_threads/get_thread). Omit for a new, unthreaded email.

    Returns:
        str: A confirmation message with the pending email id, or an error
             message if the draft could not be created or logged.
    """
    try:
        with get_db(write_engine) as db:
            create_draft_tool = all_gmail_tools_by_name.get("create_draft")
            if not create_draft_tool:
                print("Available tools:", list(all_gmail_tools_by_name.keys()))
                return
            payload = {
                "to":[customer_email],
                "subject":subject,
                "body":body,
            }
            if replyToMessageId:
                payload["replyToMessageId"] = replyToMessageId
            response = create_draft_tool.invoke(payload)
            pending_email = PendingEmailSend(tenant_id=tenant_id,thread_id=thread_id,gmail_draft_id=response["id"],customer_email=customer_email,subject=subject)
            db.add(pending_email)
            db.commit()
            db.refresh(pending_email)
            return f"Email draft successfully submitted pending email id {pending_email.id}"
    except Exception as e:
        return f"Failed to create email draft to customer: {str(e)}"


gmail_tools = [tool for tool in all_gmail_tools if tool.name in ALLOWED_TOOLS] + [create_draft]

gmail_llm = llm.bind_tools(gmail_tools)

def gmail_agent_node(state:MessagesState):
    return {"messages":[gmail_llm.invoke(state["messages"])]}


gmail_graph = StateGraph(MessagesState)
gmail_graph.add_node("agent",gmail_agent_node)
gmail_graph.add_node("tools",ToolNode(gmail_tools))
gmail_graph.add_edge(START,"agent")
gmail_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
gmail_graph.add_edge("tools","agent")

gmail_agent = gmail_graph.compile()

@tool
def gmail_specialist(query:str):
    """
    Delegate email-related customer support tasks to a dedicated Gmail specialist agent.

    Use this when the customer's request involves finding, reading, or
    replying to email correspondence — e.g. checking what was said in a
    previous email thread, or drafting a reply to send to the customer.
    This specialist can search and read Gmail threads/messages and create
    draft replies, but it can never send anything: every draft it creates
    is only ever queued for a human to review and send separately.

    Args:
        query: A natural-language description of the email task to perform,
            including any identifying details (customer email address,
            subject/topic, what the reply should say) needed to complete it.

    Returns:
        str: The specialist's response — search/read results, or
             confirmation that a draft was created and queued for review.
    """
    result = gmail_agent.invoke({"messages":HumanMessage(query)})
    return result["messages"][-1].text

specialists = [rag_specialist,db_specialist,gmail_specialist]
orchestrator_llm = llm.bind_tools(specialists + [escalate_to_human])

def orchestrator_node(state: SupportAgent):
    messages = [ORCHESTRATOR_SYSTEM_PROMPT] + state["messages"]
    return {"messages":[orchestrator_llm.invoke(messages)]}

orchestrator_graph = StateGraph(SupportAgent)
orchestrator_graph.add_node("agent",orchestrator_node)
orchestrator_graph.add_node("tools",ToolNode(specialists + [escalate_to_human]))
orchestrator_graph.add_edge(START,"agent")
orchestrator_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
orchestrator_graph.add_edge("tools","agent")

orchestrator = orchestrator_graph.compile(checkpointer=checkpointer)

def handle_incoming(query:str,thread_id:str,channel:str):
    result = orchestrator.invoke({"messages":HumanMessage(query),"channel":channel},{"configurable": {"thread_id": thread_id}})
    return result["messages"][-1].text

if __name__ == "__main__":
    messages = []
    while True:
        message = input("\nwhat is your question? ")
        if message.lower() in ["exit","q"]:
            break
        messages.append(HumanMessage(message))
        result = orchestrator.invoke({"messages":message},{"configurable": {"thread_id": thread_id}})
        reply = result["messages"][-1].text
        print(reply)
    
