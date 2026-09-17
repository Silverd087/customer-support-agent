import enum
import uuid
from datetime import datetime

from sqlalchemy import (
   UUID,
   DateTime,
   Enum,
   ForeignKey,
   String,
   Text,
   UniqueConstraint,
   func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from database.models.order import Order
    from database.models.tenant import Tenant

class Status(enum.Enum):
   PENDING_REVIEW = "pending_review"
   APPROVED = "approved"
   REJECTED = "rejected"

class PendingRefund(Base):
    __tablename__ = "pending_refunds"
    __table_args__ = (
        UniqueConstraint("tenant_id","reason","order_id",name="uix_tenant_thread_order"),
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"),nullable=False)
    customer_email:Mapped[str] = mapped_column(String(50),nullable=False)
    reason:Mapped[str] = mapped_column(Text)
    status:Mapped[Status] = mapped_column(Enum(Status,name="pending_refund_status",values_callable=lambda e: [x.value for x in e]),default=Status.PENDING_REVIEW)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    reviewed_by:Mapped[str | None] = mapped_column(Text)
    reviewed_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="pending_refunds")
    order:Mapped["Order"] = relationship("Order",back_populates="pending_refund")
