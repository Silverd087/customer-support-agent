from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
from sqlalchemy import UUID,String,DateTime,ForeignKey,Enum,Text,func,Integer,UniqueConstraint
from datetime import datetime
import enum
from typing import Optional
import uuid


class Status(enum.Enum):
    PROCESSING = "processing"
    SHIPPED =  "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"

class ShippingMethod(enum.Enum):
    STANDARD = "standard"
    EXPEDITED = "expedited"
    OVERNIGHT = "overnight"

class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id","number",name="uix_tenant_number"),
    )

    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    number:Mapped[str] = mapped_column(String(10),nullable=False)
    customer_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"),nullable=False)
    status:Mapped[Status] = mapped_column(Enum(Status,name="order_status",values_callable=lambda e: [x.value for x in e]))
    shipping_method:Mapped[ShippingMethod] = mapped_column(Enum(ShippingMethod,name="order_shipping_method",values_callable=lambda e: [x.value for x in e]))
    tracking_number:Mapped[Optional[str]] = mapped_column(String(10))
    placed_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    shipped_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    delivered_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    eta_date:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    total_cents:Mapped[int] = mapped_column(Integer)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="orders")
    customer:Mapped["Customer"] = relationship("Customer",back_populates="orders")
    order_items:Mapped[list["OrderItem"]] = relationship("OrderItem",back_populates="order")
    payments:Mapped[list["Payment"]] = relationship("Payment",back_populates="order")
    pending_refund:Mapped["PendingRefund"] = relationship("PendingRefund",back_populates="order")

