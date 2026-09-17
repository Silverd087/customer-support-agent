from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class OauthCredentials(Base):
    __tablename__ = "oauth_credentials"
    provider:Mapped[str] = mapped_column(String(100),primary_key=True)
    token_json:Mapped[dict] = mapped_column(JSONB)
    updated_at:Mapped[datetime] = mapped_column(DateTime(timezone=True),default=func.now(),onupdate=func.now())