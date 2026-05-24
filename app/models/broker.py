from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.database import Base

class Broker(Base):
    __tablename__ = "brokers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, default="Zerodha")
    encrypted_api_key = Column(String, nullable=False)
    encrypted_api_secret = Column(String, nullable=False)
    access_token = Column(String, nullable=True)
    session_active = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="brokers")
