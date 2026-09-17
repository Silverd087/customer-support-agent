import enum
import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class Status(enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REPLACEMENT_SHIPPED = "replacement_shipped"
    CLOSED = "closed"

class WarrantyClaim(Base):
    __tablename__ = "warranty_claims"

    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    order_item_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"),nullable=False)
    issue_description:Mapped[str] = mapped_column(Text)
    status:Mapped[Status] = mapped_column(Enum(Status,name="warranty_claim_status",values_callable=lambda e: [x.value for x in e]))
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="warranty_claims")
    order_item:Mapped["OrderItem"] = relationship("OrderItem",back_populates="warranty_claims")
    