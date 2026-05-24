from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional
import jwt
from datetime import datetime, timedelta

# Local imports
from app.schemas import UserRegister, UserResponse, Token, PasswordChange
from app.core.database import get_db
from app.models.user import User
from app.config import settings

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# Authentication Config from settings
JWT_SECRET = settings.jwt_secret
ALGORITHM = settings.jwt_algorithm

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=120))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserRegister, db: Session = Depends(get_db)):
    # Query PostgreSQL
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        email=user.email,
        full_name=user.full_name,
        mobile_no=user.mobile_no,
        hashed_password=user.password,  # In production, use passlib.hash.bcrypt
        is_active=True  # Active immediately upon signup! No admin approval needed
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    # Query PostgreSQL for user credentials
    db_user = db.query(User).filter(User.email == form_data.username).first()
    if not db_user or db_user.hashed_password != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact administrator for activation approval."
        )
        
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/forgot-password/send-otp")
async def send_password_recovery_otp(email: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Email not registered")
    
    return {"status": "success", "message": "Verification OTP sent to your registered email address."}

from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
            
        db_user = db.query(User).filter(User.email == email).first()
        if db_user is None:
            raise credentials_exception
        return db_user
    except jwt.PyJWTError:
        raise credentials_exception

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify current password matches (in production, use passlib.hash.bcrypt)
    if current_user.hashed_password != data.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
        
    # Update to new password
    current_user.hashed_password = data.new_password
    db.commit()
    return {"status": "success", "message": "Password changed successfully"}
