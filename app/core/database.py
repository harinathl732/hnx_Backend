from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Initialize SQLAlchemy Engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Automatically tests/recovers dropped connections
    pool_size=10,        # Pool capacity
    max_overflow=20      # Overflow capacity under heavy loads
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# FastAPI Database Session Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
