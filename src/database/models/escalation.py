from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,ForeignKey,Enum,String,Text,DateTime,func,UniqueConstraint
import enum
from datetime import datetime
from typing import Optional
class Channel(enum.Enum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    VOICE = "voice"

class Reason(enum.Enum):
    CUSTOMER_REQUESTED = "customer_requested"
    LOW_CONFIDENCE = "low_confidence"
    SECURITY_SENSITIVE = "security_sensitive"

class Status(enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"

class Escalation(Base):
    __tablename__ = "escalations"

    __table_args__ = (
        UniqueConstraint("tenant_id","thread_id","reason",name="uix_tenant_thread_reason")
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)
    thread_id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    channel:Mapped[Channel] = mapped_column(Enum(Channel,name="escalation_channel",values_callable=lambda e: [x.value for x in e]))
    customer_email:Mapped[Optional[str]] = mapped_column(String(100),nullable=True)
    summary:Mapped[str] = mapped_column(Text)
    reason:Mapped[Reason] = mapped_column(Enum(Reason,name="escalation_reason",values_callable=lambda e: [x.value for x in e]))
    status:Mapped[Status] = mapped_column(Enum(Status,name="escalation_status",values_callable=lambda e: [x.value for x in e]),default=Status.OPEN)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    resolved_by:Mapped[Optional[str]] = mapped_column(Text,nullable=True)
    resolved_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)

    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="escalations")
