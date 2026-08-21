from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,DateTime,Text,Enum,func
from datetime import datetime
import enum

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
