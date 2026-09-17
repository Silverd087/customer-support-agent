from uuid import UUID, uuid4

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert

from config import settings
from database.engines import read_engine, write_engine
from database.models.customer import Customer
from database.models.escalation import Escalation
from database.models.order import Order
from database.models.order_item import OrderItem
from database.models.order_return import OrderReturn
from database.models.pending_refund import PendingRefund
from database.models.product import Product
from database.models.subscription import Subscription
from database.models.warranty_claim import WarrantyClaim
from database.session import get_db
from logger import logger
from retries import invoke_with_retry, run_query_with_retry

load_dotenv()

thread_id = uuid4()
tenant_id = UUID("a0000000-0000-0000-0000-000000000001")
llm = ChatGoogleGenerativeAI(api_key=settings.google_api_key,model="gemini-2.5-flash")

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
            status = run_query_with_retry(lambda:db.scalar(stmt))
            if status is None:
                return "Order not found or email does not match."
            return status.value if hasattr(status, "value") else str(status)
    except Exception as e:
        return f"Failed to fetch order: {e!s}"

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
            order = run_query_with_retry(lambda:db.execute(stmt).scalar_one_or_none())
            if not order:
                return "Order not found or email does not match."
            insert_stmt = insert(PendingRefund).values(order_id=order.id,customer_email=customer_email,reason=reason,tenant_id=tenant_id).on_conflict_do_nothing(index_elements=["tenant_id","reason","order_id"]).returning(PendingRefund)
            refund = run_query_with_retry(lambda:db.scalars(insert_stmt).one_or_none())
            db.commit()
            if refund is None:
                stmt = select(PendingRefund).where(PendingRefund.order_id == order.id, PendingRefund.reason == reason, PendingRefund.tenant_id == tenant_id)
                refund = run_query_with_retry(lambda: db.execute(stmt).scalar_one_or_none())
                logger.info("refund_request_deduped", refund_id=str(refund.id) if refund else None, order_number=order_number)
            else:
                logger.info("refund_request_created", refund_id=str(refund.id), order_number=order_number)
            refund_id = refund.id
            ref_info = f" (Refund ID: {refund_id})" if refund_id else ""

            return f"Refund request successfully submitted{ref_info} for order '{order_number}'."
    except Exception as e:
        logger.error("refund_request_failed", order_number=order_number, error=str(e))
        return f"Failed to submit refund request: {e!s}"

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
            subs = run_query_with_retry(lambda:db.scalars(stmt).all())
            if subs == []:
                return "Subscription not found or email does not match."
            lines = [
                f"{sub.plan.value} plan ({sub.billing_cycle.value}): {sub.status.value}, "
                f"period {sub.current_period_start} to {sub.current_period_end}"
                for sub in subs
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch subscription: {e!s}"

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
            claims = run_query_with_retry(lambda:db.scalars(stmt).all())
            if claims == []:
                return "warranty claim not found or email does not match."
            lines = [
                f"{claim.order_item.product.name}: {claim.status.value} "
                f"(filed {claim.created_at.date()}) — \"{claim.issue_description}\""
                for claim in claims
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch warranty claim: {e!s}"
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
            returns = run_query_with_retry(lambda:db.scalars(stmt).all())
            if returns == []:
                return "order return not found or email does not match."
            lines = [
                f"{r.order_item.product.name}: {r.status.value} "
                f"(filed {r.requested_at.date()}) — \"{r.reason}\""
                for r in returns
            ]
            return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch order return: {e!s}"
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
            order_item = run_query_with_retry(lambda:db.execute(stmt).scalar_one_or_none())
            if not order_item:
                return "Order item not found or email does not match."
            order_return = OrderReturn(order_item_id=order_item.id,reason=reason,tenant_id=tenant_id)
            insert_stmt = insert(OrderReturn).values(order_item_id=order_item.id,reason=reason,tenant_id=tenant_id).on_conflict_do_nothing(index_elements=["order_item_id","reason","tenant_id"]).returning(OrderReturn)
            order_return = run_query_with_retry(lambda:db.scalars(insert_stmt).one_or_none())
            db.commit()
            if order_return is None:
                stmt = select(OrderReturn).where(OrderReturn.order_item_id == order_item.id, OrderReturn.reason == reason, OrderReturn.tenant_id == tenant_id)
                order_return = run_query_with_retry(lambda:db.execute(stmt).scalar_one_or_none())
                logger.info("return_request_deduped", return_id=str(order_return.id) if order_return else None, order_number=order_number, product_name=product_name)
            else:
                logger.info("return_request_created", return_id=str(order_return.id), order_number=order_number, product_name=product_name)
            return_id = order_return.id

            return f"Return request successfully submitted for product {product_name} for order '{order_number}' return id {return_id}."
    except Exception as e:
        logger.error("return_request_failed", order_number=order_number, product_name=product_name, error=str(e))
        return f"Failed to submit order return request: {e!s}"

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
            insert_stmt = insert(Escalation).values(reason=reason,summary=summary,customer_email=customer_email,channel=channel,tenant_id=tenant_id,thread_id=thread_id).on_conflict_do_nothing(index_elements=["tenant_id","reason","thread_id"]).returning(Escalation)
            escalation = run_query_with_retry(lambda:db.scalars(insert_stmt).one_or_none())
            db.commit()
            if escalation is None:
                stmt = select(Escalation).where(Escalation.reason == reason, Escalation.tenant_id == tenant_id,Escalation.thread_id == thread_id)
                escalation = run_query_with_retry(lambda:db.execute(stmt).scalar_one_or_none())
                logger.info("escalation_deduped", escalation_id=str(escalation.id) if escalation else None, reason=reason, channel=channel, thread_id=str(thread_id))
            else:
                logger.warning("escalation_created", escalation_id=str(escalation.id), reason=reason, channel=channel, thread_id=str(thread_id))
            escalation_id = escalation.id

            return f"Escalation request successfully submitted escalation id {escalation_id}"
    except Exception as e:
        logger.error("escalation_failed", reason=reason, channel=channel, thread_id=str(thread_id), error=str(e))
        return f"Failed to escalate request to human agent: {e!s}"


db_tools = [get_order_status,create_refund_request,get_subscription_status,get_warranty_claim_status,get_return_status,create_return_request,escalate_to_human]
db_llm = llm.bind_tools(db_tools)
def db_agent_node(state: MessagesState):
    return {"messages":[invoke_with_retry(db_llm,state["messages"])]}

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