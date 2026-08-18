from base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,String,Enum,Integer,Boolean,ForeignKey
import enum

class Category(enum.Enum):
    PLUG = "plug"
    CAMERA = "camera"
    SENSOR = "sensor"
    THERMOSTAT = "thermostat"

class Product(Base):
    __tablename__ = "product"
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    sku:Mapped[str] = mapped_column(String(50),unique=True)
    name:Mapped[str] = mapped_column(String(50))
    category:Mapped[Category] = mapped_column(Enum(Category),values_callable=lambda e: [x.value for x in e])
    price_cents:Mapped[int] = mapped_column(Integer,nullable=False)
    active:Mapped[bool] = mapped_column(Boolean,default=True,nullable=False)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="products")
    order_items:Mapped[list["OrderItem"]] = relationship("OrderItem",back_populates="product")