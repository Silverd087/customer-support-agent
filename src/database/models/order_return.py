import enum
import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class Status(enum.Enum):
    REQUESTED = "requested"
    LABEL_GENERATED = "label_generated"
    RECEIVED = "received"
    REFUNDED = 'refunded'

class OrderReturn(Base):
    __tablename__ = "order_returns"

    __table_args__ = (
        UniqueConstraint("order_item_id","reason","tenant_id",name="uix_tenat_reason_order_item"),
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_item_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"))
    reason:Mapped[str] = mapped_column(Text)
    status:Mapped[Status] = mapped_column(Enum(Status,name="order_return_status",values_callable=lambda e: [x.value for x in e]))
    requested_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    refunded_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="order_returns")
    order_item:Mapped["OrderItem"] = relationship("OrderItem",back_populates="order_returns")