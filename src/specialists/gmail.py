import asyncio
import hashlib
import sys
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from database.engines import write_engine
from database.models.pending_email_send import PendingEmailSend
from database.session import get_db
from gmail_credentials import get_gmail_headers
from logger import logger
from retries import invoke_with_retry, run_query_with_retry

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ALLOWED_TOOLS = ["search_threads","get_thread","get_message"]
thread_id = uuid4()
load_dotenv()

llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")
tenant_id = UUID("a0000000-0000-0000-0000-000000000001")

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
def create_draft(customer_email:str,subject:str,body:str,reply_to_message_id:str | None=None):
    """
    Create a draft reply email to a customer and queue it for human approval.

    This never sends anything. It creates a Gmail draft via the Gmail MCP
    connection and logs a 'pending_review' row for a human to review and
    send later — the send step happens outside this conversation entirely.

    Args:
        customer_email: The recipient's email address.
        subject: The subject line for the draft.
        body: The plain-text body of the draft.
        reply_to_message_id: The id of the message being replied to, if this
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
                logger.error("gmail_create_draft_tool_missing", available_tools=list(all_gmail_tools_by_name.keys()))
                return
            payload = {
                "to":[customer_email],
                "subject":subject,
                "body":body,
            }
            if reply_to_message_id:
                payload["replyToMessageId"] = reply_to_message_id
            else:
                content = f"{subject}\0{body}".encode()
                reply_to_message_id = hashlib.sha256(content).hexdigest()
            insert_stmt = insert(PendingEmailSend).values(tenant_id=tenant_id,thread_id=thread_id,customer_email=customer_email,subject=subject,reply_to_message_id = reply_to_message_id).on_conflict_do_nothing(index_elements=["tenant_id","thread_id","reply_to_message_id"]).returning(PendingEmailSend)
            pending_email = run_query_with_retry(lambda: db.scalars(insert_stmt).one_or_none())
            db.commit()
            if pending_email is None:
                stmt = select(PendingEmailSend).where(PendingEmailSend.tenant_id == tenant_id, PendingEmailSend.thread_id == thread_id, PendingEmailSend.reply_to_message_id == reply_to_message_id)
                pending_email = run_query_with_retry(lambda:db.execute(stmt).scalar_one_or_none())
                logger.info("draft_request_deduped", pending_email_id=str(pending_email.id) if pending_email else None, thread_id=str(thread_id))
            else:
                response = call_create_draft_with_retry(create_draft_tool,payload)
                stmt = update(PendingEmailSend).where(PendingEmailSend.tenant_id == tenant_id, PendingEmailSend.thread_id == thread_id, PendingEmailSend.reply_to_message_id == reply_to_message_id).values(gmail_draft_id=response["id"])
                run_query_with_retry(lambda: db.execute(stmt))
                db.commit()
                logger.info("draft_created", pending_email_id=str(pending_email.id), gmail_draft_id=response["id"], customer_email=customer_email, thread_id=str(thread_id))
            return f"Email draft successfully submitted pending email id {pending_email.id}"
    except Exception as e:
        logger.error("draft_creation_failed", customer_email=customer_email, thread_id=str(thread_id), error=str(e))
        return f"Failed to create email draft to customer: {e!s}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type((httpx.ReadTimeout,httpx.ConnectError,httpx.RemoteProtocolError)))
def call_create_draft_with_retry(gmail_tool,message):
    return gmail_tool.invoke(message)

gmail_tools = [tool for tool in all_gmail_tools if tool.name in ALLOWED_TOOLS] + [create_draft]

gmail_llm = llm.bind_tools(gmail_tools)

def gmail_agent_node(state:MessagesState):
    return {"messages":[invoke_with_retry(gmail_llm,state["messages"])]}


gmail_graph = StateGraph(MessagesState)
gmail_graph.add_node("agent",gmail_agent_node)
gmail_graph.add_node("tools",ToolNode(gmail_tools))
gmail_graph.add_edge(START,"agent")
gmail_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
gmail_graph.add_edge("tools","agent")

gmail_agent = gmail_graph.compile()

@tool
async def gmail_specialist(query:str):
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
    result = await gmail_agent.ainvoke({"messages":HumanMessage(query)})
    return result["messages"][-1].text