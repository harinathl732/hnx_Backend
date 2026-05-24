from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    mobile_no = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)  # Awaiting Admin Activation
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    brokers = relationship("Broker", back_populates="user", cascade="all, delete-orphan")
    strategies = relationship("UserStrategy", back_populates="user", cascade="all, delete-orphan")
