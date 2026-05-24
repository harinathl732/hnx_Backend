from sqlalchemy import Column, String, Boolean, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.database import Base

class UserStrategy(Base):
    __tablename__ = "user_strategies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(String, nullable=False)  # "nifty_momentum" or "banknifty_reversal"
    lot_size = Column(Integer, default=1)
    multiplier = Column(Integer, default=1)
    mtm_enabled = Column(Boolean, default=True)
    mtm_max_loss = Column(Numeric(10, 2), default=3000.0)
    mtm_max_profit = Column(Numeric(10, 2), default=8000.0)
    is_active = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="strategies")
