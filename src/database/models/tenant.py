import enum
import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from database.models.order import Order
    from database.models.subscription import Subscription
    from database.models.payment import Payment
    from database.models.order_item import OrderItem
    from database.models.customer import Customer
    from database.models.order_return import OrderReturn
    from database.models.pending_refund import PendingRefund
    from database.models.product import Product
    from database.models.warranty_claim import WarrantyClaim
    from database.models.escalation import Escalation
    from database.models.pending_email_send import PendingEmailSend

class Plan(enum.Enum):
    TRIAL = "trial"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class Status(enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"

class Tenant(Base):
    __tablename__ = "tenants"
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    name:Mapped[str] = mapped_column(Text,nullable=False)
    slug:Mapped[str] = mapped_column(Text,nullable=False)
    plan:Mapped[Plan] = mapped_column(Enum(Plan,name="tenant_plan",values_callable=lambda e: [x.value for x in e]))
    status:Mapped[Status] = mapped_column(Enum(Status,name="tenant_status",values_callable=lambda e: [x.value for x in e]))
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())

    customers:Mapped[list["Customer"]] = relationship("Customer",back_populates="tenant")
    order_items:Mapped[list["OrderItem"]] = relationship("OrderItem",back_populates="tenant")
    order_returns:Mapped[list["OrderReturn"]] = relationship("OrderReturn",back_populates="tenant")
    orders:Mapped[list["Order"]] = relationship("Order",back_populates="tenant")
    payments:Mapped[list["Payment"]] = relationship("Payment",back_populates="tenant")
    pending_refunds:Mapped[list["PendingRefund"]] = relationship("PendingRefund",back_populates="tenant")
    products:Mapped[list["Product"]] = relationship("Product",back_populates="tenant")
    warranty_claims:Mapped[list["WarrantyClaim"]] = relationship("WarrantyClaim",back_populates="tenant")
    subscriptions:Mapped[list["Subscription"]] = relationship("Subscription",back_populates="tenant")
    escalations:Mapped[list["Escalation"]] = relationship("Escalation",back_populates="tenant")
    pending_email_sends:Mapped[list["PendingEmailSend"]] = relationship("PendingEmailSend",back_populates="tenant")
