from base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,ForeignKey,DateTime,Text,func,Enum
from datetime import datetime
from typing import Optional
import enum

class Status(enum.Enum):
    REQUESTED = "requested"
    LABEL_GENERATED = "label_generated"
    RECEIVED = "received"
    REFUNDED = 'refunded'

class OrderReturn(Base):
    __tablename__ = "order_return"

    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_item_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("order_item.id"))
    reason:Mapped[str] = mapped_column(Text)
    status:Mapped[Status] = mapped_column(Enum(Status),values_callable=lambda e: [x.value for x in e])
    requested_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    refunded_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="order_returns")
    order_item:Mapped["OrderItem"] = relationship("OrderItem",back_populates="order_returns")