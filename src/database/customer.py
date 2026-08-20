from database.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,String,DateTime,ForeignKey,func,UniqueConstraint
from typing import Optional
from datetime import datetime

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id","email",name="uix_tenant_email"),
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    email:Mapped[str] = mapped_column(String(100))
    full_name:Mapped[str] = mapped_column(String(100))
    household_id:Mapped[Optional[uuid.UUID]] =  mapped_column(ForeignKey("customers.id"),nullable=True)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="customers")
    household:Mapped["Customer"] = relationship("Customer",remote_side=[id])
    orders:Mapped[list["Order"]] = relationship("Order",back_populates="customer")
    subscriptions:Mapped[list["Subscription"]] = relationship("Subscription",back_populates="customer")
    payments:Mapped[list["Payment"]] = relationship("Payment",back_populates="customer")