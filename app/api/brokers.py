from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Dict
import jwt

# Local imports
from app.schemas import BrokerCredentials
from app.core.engine import trading_engine
from app.core.database import get_db
from app.models.user import User
from app.models.broker import Broker
from app.config import settings

router = APIRouter(
    prefix="/brokers",
    tags=["Broker Integration"]
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
            
        # Fetch current active user mapping from Postgres
        db_user = db.query(User).filter(User.email == email).first()
        if db_user is None:
            raise credentials_exception
        return db_user
    except jwt.PyJWTError:
        raise credentials_exception

@router.get("/zerodha/credentials", response_model=Dict[str, str])
async def get_zerodha_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_broker = db.query(Broker).filter(Broker.user_id == current_user.id).first()
    if not db_broker:
        raise HTTPException(status_code=404, detail="Broker credentials not configured")
    
    return {
        "api_key": db_broker.encrypted_api_key,
        "api_secret": "•" * 12
    }

@router.post("/zerodha/credentials")
async def save_zerodha_credentials(
    creds: BrokerCredentials,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_broker = db.query(Broker).filter(Broker.user_id == current_user.id).first()
    if db_broker:
        # Update existing
        db_broker.encrypted_api_key = creds.api_key
        db_broker.encrypted_api_secret = creds.api_secret
        db_broker.session_active = False
        db_broker.access_token = None
    else:
        # Create new
        new_broker = Broker(
            user_id=current_user.id,
            encrypted_api_key=creds.api_key,
            encrypted_api_secret=creds.api_secret,
            session_active=False
        )
        db.add(new_broker)
        
    # Also clean up running trading engine sessions if any exist
    if current_user.email in trading_engine.active_sessions:
        del trading_engine.active_sessions[current_user.email]
        
    db.commit()
    return {"status": "success", "message": "API credentials saved in PostgreSQL database"}

@router.get("/zerodha/status")
async def get_zerodha_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_broker = db.query(Broker).filter(Broker.user_id == current_user.id).first()
    if not db_broker:
        return {
            "configured": False,
            "session_active": False,
            "api_key": ""
        }
    
    # Active if present in active_sessions and session_active is True
    is_engine_active = current_user.email in trading_engine.active_sessions
    session_active = db_broker.session_active and is_engine_active
    
    # Sync database state if they differ
    if db_broker.session_active != session_active:
        db_broker.session_active = session_active
        db.commit()
        
    return {
        "configured": True,
        "session_active": session_active,
        "api_key": db_broker.encrypted_api_key
    }


@router.get("/zerodha/url")
async def get_zerodha_login_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_broker = db.query(Broker).filter(Broker.user_id == current_user.id).first()
    if not db_broker:
        raise HTTPException(status_code=400, detail="Configure API key and secret first")
    
    # Store the user's email in the 'state' parameter to identify them securely in the redirect callback!
    login_url = f"https://kite.zerodha.com/connect/login?api_key={db_broker.encrypted_api_key}&v=3&state={current_user.email}"
    return {"login_url": login_url}

@router.get("/zerodha/callback", response_class=HTMLResponse)
async def zerodha_callback(
    request_token: str,
    state: str,
    db: Session = Depends(get_db)
):
    # Find user using the email passed inside the state parameter!
    db_user = db.query(User).filter(User.email == state).first()
    if not db_user:
        return HTMLResponse("<h3>Authentication Error: User session invalid.</h3>")

    db_broker = db.query(Broker).filter(Broker.user_id == db_user.id).first()
    if not db_broker:
        return HTMLResponse("<h3>Authentication Error: Broker credentials not configured.</h3>")
    
    success = await trading_engine.initialize_session(
        user_id=db_user.email,
        api_key=db_broker.encrypted_api_key,
        api_secret=db_broker.encrypted_api_secret,
        request_token=request_token
    )
    
    if not success:
        return HTMLResponse("<h3>Authentication Error: KiteConnect Session authentication failed.</h3>")
    
    db_broker.session_active = True
    db_broker.access_token = request_token  # Store the real access token
    db.commit()
    
    # Render premium interactive dashboard redirect page
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>HNX Quantum - Session Authenticated</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body {
                background-color: #05060f;
                color: #ffffff;
                font-family: 'Outfit', sans-serif;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .card {
                background-color: #0b0c16;
                border: 1px solid rgba(0, 255, 135, 0.25);
                padding: 3rem;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0, 255, 135, 0.1);
                max-width: 450px;
            }
            .icon {
                font-size: 4rem;
                color: #00ff87;
                margin-bottom: 1.5rem;
                animation: scaleIn 0.5s ease-out;
            }
            h1 {
                font-size: 1.8rem;
                margin-bottom: 0.5rem;
            }
            p {
                color: #9ca3af;
                font-size: 0.95rem;
                line-height: 1.5;
                margin-bottom: 2rem;
            }
            .btn {
                background: linear-gradient(135deg, #ff7b00, #ffb700);
                color: #080914;
                padding: 0.75rem 2rem;
                border-radius: 12px;
                font-weight: 700;
                text-decoration: none;
                display: inline-block;
                cursor: pointer;
                border: none;
                transition: transform 0.2s;
            }
            .btn:hover {
                transform: scale(1.05);
            }
            @keyframes scaleIn {
                from { transform: scale(0); opacity: 0; }
                to { transform: scale(1); opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✓</div>
            <h1>Broker Authenticated</h1>
            <p>Your Zerodha Kite session was successfully verified and linked to your HNX Quantum terminal!</p>
            <button class="btn" onclick="returnToDashboard()">Return to Dashboard</button>
        </div>
        <script>
            function returnToDashboard() {
                // Try to go back to referring page, or default to local frontend
                const ref = document.referrer;
                if (ref && ref.includes('hnxquantum.in')) {
                    window.location.href = 'https://hnxquantum.in/dashboard.html';
                } else {
                    window.location.href = '../smart3algo-frontend/dashboard.html';
                }
            }
            // Auto redirect in 3 seconds
            setTimeout(returnToDashboard, 3000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
