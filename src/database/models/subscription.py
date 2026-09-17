import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UUID, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.customer import Customer
    from database.models.payment import Payment
    from database.models.tenant import Tenant

class Plan(enum.Enum):
    INDIVIDUAL = "individual"
    FAMILY  = "family"

class BillingCycle(enum.Enum):
    MONTHLY = "monthly"
    ANNUALLY = "annually"

class Status(enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"

class Subscription(Base):
    __tablename__ = "subscriptions"
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    customer_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"),nullable=False)
    plan:Mapped[Plan] = mapped_column(Enum(Plan,name="subscription_plan",values_callable=lambda e: [x.value for x in e]))
    billing_cycle:Mapped[BillingCycle] = mapped_column(Enum(BillingCycle,name="subscription_billing_cycle",values_callable=lambda e: [x.value for x in e]))
    status:Mapped[Status] = mapped_column(Enum(Status,name="subscription_status",values_callable=lambda e: [x.value for x in e]))
    current_period_start:Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    current_period_end:Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    cancelled_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="subscriptions")
    customer:Mapped["Customer"] = relationship("Customer",back_populates="subscriptions")
    payments:Mapped[list["Payment"]] = relationship("Payment",back_populates="subscription")

