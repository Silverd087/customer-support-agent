from database.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String,DateTime,func
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

class OauthCredentials(Base):
    __tablename__ = "oauth_credentials"
    provider:Mapped[str] = mapped_column(String(100),primary_key=True)
    token_json:Mapped[dict] = mapped_column(JSONB)
    updatedAt:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now(),onupdate=func.now())