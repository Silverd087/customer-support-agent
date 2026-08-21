from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,ForeignKey,Enum,Integer,DateTime
import enum
from datetime import datetime
from typing import Optional

class Status(enum.Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"

class Payment(Base):
    __tablename__ = "payments"
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    customer_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"),nullable=False)
    order_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"),nullable=True)
    subscription_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id"),nullable=True)
    amount_cents:Mapped[int] = mapped_column(Integer)
    status:Mapped[Status] = mapped_column(Enum(Status,name="payment_status",values_callable=lambda e: [x.value for x in e]))
    charged_at:Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="payments")
    customer:Mapped["Customer"] = relationship("Customer",back_populates="payments")
    order:Mapped[Optional["Order"]] = relationship("Order",back_populates="payments")
    subscription:Mapped[Optional["Subscription"]] = relationship("Subscription",back_populates="payments")
