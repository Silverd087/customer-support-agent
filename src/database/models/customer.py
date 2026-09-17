import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UUID, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from database.models.order import Order
    from database.models.payment import Payment
    from database.models.subscription import Subscription
    from database.models.tenant import Tenant

from database.models.base import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id","email",name="uix_tenant_email"),
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    email:Mapped[str] = mapped_column(String(100))
    full_name:Mapped[str] = mapped_column(String(100))
    household_id:Mapped[uuid.UUID | None] =  mapped_column(ForeignKey("customers.id"),nullable=True)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="customers")
    household:Mapped["Customer"] = relationship("Customer",remote_side=[id])
    orders:Mapped[list["Order"]] = relationship("Order",back_populates="customer")
    subscriptions:Mapped[list["Subscription"]] = relationship("Subscription",back_populates="customer")
    payments:Mapped[list["Payment"]] = relationship("Payment",back_populates="customer")