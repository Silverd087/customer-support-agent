import asyncio
from typing import Annotated, TypedDict
from uuid import UUID

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg_pool import AsyncConnectionPool
from redis.exceptions import RedisError

import database.models  # noqa: F401
from cache import redis_cache
from config import settings
from logger import logger
from retries import invoke_with_retry
from specialists import db_specialist, gmail_specialist, rag_specialist

load_dotenv()

EXPIRATION_TIME = 600
RATE_LIMIT_THRESHOLD = 5
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
db_uri = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:5432/{settings.db_name}"

async def _init_checkpointer():
    pool = AsyncConnectionPool(conninfo=db_uri,min_size=1,max_size=20, kwargs={"autocommit": True, "prepare_threshold": 0},open=False)
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return checkpointer

checkpointer = asyncio.run(_init_checkpointer())

tenant_id = UUID("a0000000-0000-0000-0000-000000000001")
llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")


class SupportAgent(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]
    channel:str

specialists = [rag_specialist,db_specialist,gmail_specialist]
orchestrator_llm = llm.bind_tools(specialists)

def orchestrator_node(state: SupportAgent):
    messages = [ORCHESTRATOR_SYSTEM_PROMPT] + state["messages"]
    return {"messages":[invoke_with_retry(orchestrator_llm,messages)]}

orchestrator_graph = StateGraph(SupportAgent)
orchestrator_graph.add_node("agent",orchestrator_node)
orchestrator_graph.add_node("tools",ToolNode(specialists))
orchestrator_graph.add_edge(START,"agent")
orchestrator_graph.add_conditional_edges("agent",tools_condition,{"tools":"tools",END:END})
orchestrator_graph.add_edge("tools","agent")

orchestrator = orchestrator_graph.compile(checkpointer=checkpointer)

async def handle_incoming(query:str,thread_id:str,channel:str):
    key = f"ratelimit:{channel}:{thread_id}"
    try:
        count = redis_cache.incr(key)
        if count == 1:
            redis_cache.expire(key,EXPIRATION_TIME)
        if count > RATE_LIMIT_THRESHOLD:
            logger.warning("rate_limit_exceeded", channel=channel, thread_id=str(thread_id), count=count)
            return "rate limit exceeded, wait a few minutes before making another request"
    except RedisError as e:
        logger.error("redis_error", channel=channel, thread_id=str(thread_id), error=str(e))
    result = await orchestrator.ainvoke({"messages":[HumanMessage(query)],"channel":channel},{"configurable": {"thread_id": thread_id},"metadata":{"thread_id":thread_id}})
    logger.info("turn_completed", channel=channel, thread_id=str(thread_id))
    return result["messages"][-1].text