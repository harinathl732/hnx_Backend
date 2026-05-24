from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Dict
import jwt

# Local imports
from app.schemas import StrategyResponse, StrategySettings, LivePnLResponse
from app.core.engine import trading_engine
from app.core.database import get_db
from app.models.user import User
from app.models.strategy import UserStrategy
from app.config import settings

router = APIRouter(
    prefix="/user",
    tags=["Strategies & PnL"]
)

# Authentication Config from settings
JWT_SECRET = settings.jwt_secret
ALGORITHM = settings.jwt_algorithm
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
            
        db_user = db.query(User).filter(User.email == email).first()
        if db_user is None:
            raise credentials_exception
        return db_user
    except jwt.PyJWTError:
        raise credentials_exception

# Default system strategies catalog
SYSTEM_STRATEGIES = {
    "time_formula_35pts": {
        "name": "Algo version of Nifty Time Formula Breakout Strategy (9:16)",
        "index": "NIFTY",
        "description": "At 9:16 AM, identify ATM CE/PE and mark the 1-Min Close. Enter CE long if price moves above marked close, PE long if below. Features candle-close 15/20-pt SL, trailing SL to breakeven at +30 pts, 35-pt Target, and Martingale lot scaling (increases on SL, resets on Target).",
        "default_settings": {"lot_size": 1, "multiplier": 1, "mtm_enabled": True, "mtm_max_loss": 3000.0, "mtm_max_profit": 8000.0}
    }
}


@router.get("/strategies", response_model=List[StrategyResponse])
async def get_user_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    results = []
    for strat_id, info in SYSTEM_STRATEGIES.items():
        # Query user-specific strategy config in PostgreSQL
        db_strat = db.query(UserStrategy).filter(
            UserStrategy.user_id == current_user.id,
            UserStrategy.strategy_id == strat_id
        ).first()
        
        if db_strat:
            active = db_strat.is_active
            settings_dict = {
                "lot_size": db_strat.lot_size,
                "multiplier": db_strat.multiplier,
                "mtm_enabled": db_strat.mtm_enabled,
                "mtm_max_loss": float(db_strat.mtm_max_loss),
                "mtm_max_profit": float(db_strat.mtm_max_profit)
            }
        else:
            active = False
            settings_dict = info["default_settings"]
            
        results.append({
            "id": strat_id,
            "name": info["name"],
            "index": info["index"],
            "description": info["description"],
            "active": active,
            "settings": settings_dict
        })
    return results

@router.post("/strategy/settings")
async def update_strategy_settings(
    settings_payload: StrategySettings, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if settings_payload.strategy_id not in SYSTEM_STRATEGIES:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    db_strat = db.query(UserStrategy).filter(
        UserStrategy.user_id == current_user.id,
        UserStrategy.strategy_id == settings_payload.strategy_id
    ).first()
    
    settings_dict = {
        "lot_size": settings_payload.lot_size,
        "multiplier": settings_payload.multiplier,
        "mtm_enabled": settings_payload.mtm_enabled,
        "mtm_max_loss": settings_payload.mtm_max_loss,
        "mtm_max_profit": settings_payload.mtm_max_profit
    }
    
    if db_strat:
        db_strat.lot_size = settings_payload.lot_size
        db_strat.multiplier = settings_payload.multiplier
        db_strat.mtm_enabled = settings_payload.mtm_enabled
        db_strat.mtm_max_loss = settings_payload.mtm_max_loss
        db_strat.mtm_max_profit = settings_payload.mtm_max_profit
    else:
        new_strat = UserStrategy(
            user_id=current_user.id,
            strategy_id=settings_payload.strategy_id,
            lot_size=settings_payload.lot_size,
            multiplier=settings_payload.multiplier,
            mtm_enabled=settings_payload.mtm_enabled,
            mtm_max_loss=settings_payload.mtm_max_loss,
            mtm_max_profit=settings_payload.mtm_max_profit,
            is_active=False
        )
        db.add(new_strat)
        
    db.commit()
    
    # Update execution settings dynamically in the running task engine
    await trading_engine.update_live_settings(current_user.email, settings_payload.strategy_id, settings_dict)
    
    return {"status": "success", "message": "Strategy risk parameters saved in PostgreSQL"}

@router.post("/strategy/control")
async def control_strategy(
    strategy_id: str = Query(...),
    action: str = Query(...),  # "start", "stop"
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if strategy_id not in SYSTEM_STRATEGIES:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    db_strat = db.query(UserStrategy).filter(
        UserStrategy.user_id == current_user.id,
        UserStrategy.strategy_id == strategy_id
    ).first()
    
    # Get current strategy parameters
    if db_strat:
        settings_dict = {
            "lot_size": db_strat.lot_size,
            "multiplier": db_strat.multiplier,
            "mtm_enabled": db_strat.mtm_enabled,
            "mtm_max_loss": float(db_strat.mtm_max_loss),
            "mtm_max_profit": float(db_strat.mtm_max_profit)
        }
    else:
        # Load from defaults
        settings_dict = SYSTEM_STRATEGIES[strategy_id]["default_settings"]
        
    if action == "start":
        if current_user.email not in trading_engine.active_sessions:
            raise HTTPException(status_code=400, detail="Link your active broker session before running algorithms")
            
        if db_strat:
            db_strat.is_active = True
        else:
            db_strat = UserStrategy(
                user_id=current_user.id,
                strategy_id=strategy_id,
                is_active=True,
                **settings_dict
            )
            db.add(db_strat)
            
        db.commit()
        await trading_engine.start_strategy(current_user.email, strategy_id, settings_dict)
        
    elif action == "stop":
        if db_strat:
            db_strat.is_active = False
            db.commit()
        await trading_engine.stop_strategy(current_user.email, strategy_id)
        
    else:
        raise HTTPException(status_code=400, detail="Invalid strategy action override")
        
    return {"status": "success", "strategy_id": strategy_id, "active": db_strat.is_active}

@router.get("/live-pnl", response_model=LivePnLResponse)
async def get_live_pnl(current_user: User = Depends(get_current_user)):
    pnl_data = await trading_engine.get_live_pnl(current_user.email)
    return pnl_data
