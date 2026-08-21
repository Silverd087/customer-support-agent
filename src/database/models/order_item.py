from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,ForeignKey,Integer


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"),nullable=False)
    product_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"),nullable=False)
    quantity:Mapped[int] = mapped_column(Integer)
    unit_price_cents:Mapped[int] = mapped_column(Integer)
    warranty_months:Mapped[int] = mapped_column(Integer)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="order_items")
    order:Mapped["Order"] = relationship("Order",back_populates="order_items")
    product:Mapped["Product"] = relationship("Product",back_populates="order_items")
    order_returns:Mapped[list["OrderReturn"]] = relationship("OrderReturn",back_populates="order_item")
    warranty_claims:Mapped[list["WarrantyClaim"]] = relationship("WarrantyClaim",back_populates="order_item")

