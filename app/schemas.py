from pydantic import BaseModel, EmailStr, Field
from typing import Dict, List, Optional

class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    mobile_no: str
    password: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class UserResponse(BaseModel):
    email: EmailStr
    full_name: str
    mobile_no: str
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class StrategySettings(BaseModel):
    strategy_id: str
    lot_size: int = Field(gt=0, default=1)
    multiplier: int = Field(gt=0, default=1)
    mtm_enabled: bool = True
    mtm_max_loss: float = Field(gt=0.0, default=5000.0)
    mtm_max_profit: float = Field(gt=0.0, default=12000.0)

class BrokerCredentials(BaseModel):
    api_key: str
    api_secret: str

class StrategyResponse(BaseModel):
    id: str
    name: str
    index: str
    description: str
    active: bool
    settings: Dict

class LivePnLResponse(BaseModel):
    user_id: str
    live_pnl: float
    status: str  # "active", "profit_hit", "loss_hit", "inactive"
    timestamp: str
    active_positions_count: int
