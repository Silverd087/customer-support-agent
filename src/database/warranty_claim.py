from base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,ForeignKey,Enum,DateTime,Text,func
import enum
from datetime import datetime


class Status(enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REPLACEMENT_SHIPPED = "replacement_shipped"
    CLOSED = "closed"

class WarrantyClaim(Base):
    __tablename__ = "warranty_claim"

    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_item_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("order_item.id"),nullable=False)
    issue_description:Mapped[str] = mapped_column(Text)
    status:Mapped[Status] = mapped_column(Enum(Status),values_callable=lambda e: [x.value for x in e])
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="warranty_claims")
    order_item:Mapped["OrderItem"] = relationship("OrderItem",back_populates="warranty_claims")
    