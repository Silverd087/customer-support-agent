from database.models.base import Base
from sqlalchemy.orm import mapped_column,Mapped,relationship
import uuid
from sqlalchemy import UUID,String,DateTime,ForeignKey,Text,Enum,func,UniqueConstraint
from typing import Optional
from datetime import datetime
import enum

class Status(enum.Enum):
   PENDING_REVIEW = "pending_review"
   APPROVED = "approved"
   REJECTED = "rejected"
   SENT = "sent"
 
class PendingEmailSend(Base):
    __tablename__ = "pending_email_sends"
    __table_args__ = (
        UniqueConstraint("tenant_id","thread_id","replyToMessageId",name="uix_tenant_thread_reply_id"),
    )
    id:Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    tenant_id:Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"),nullable=False)
    thread_id:Mapped[str] = mapped_column(Text,nullable=False)
    gmail_draft_id:Mapped[str] = mapped_column(Text,nullable=False)
    customer_email:Mapped[str] = mapped_column(String(100),nullable=False)
    subject:Mapped[str] = mapped_column(Text,nullable=False)
    status:Mapped[Status] = mapped_column(Enum(Status,name="pending_email_send_status",values_callable=lambda e: [x.value for x in e]),default=Status.PENDING_REVIEW)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now())
    reviewed_by:Mapped[Optional[str]] = mapped_column(Text,nullable=True)
    reviewed_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    sent_at:Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    replyToMessageId:Mapped[Optional[str]] = mapped_column(String(100))


    tenant:Mapped["Tenant"] = relationship("Tenant",back_populates="pending_email_sends")
