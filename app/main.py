import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Local imports
from app.api import auth, brokers, strategies
from app.core.database import engine, Base
import app.models  # Load models to bind metadata

# Automatically create PostgreSQL tables on startup
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"PostgreSQL Database Linkage Delayed: {e}")

app = FastAPI(
    title="HNX Quantum Backend - Scalable FastAPI Platform",
    description="Scalable modular backend system featuring dedicated routers for Authentication, Brokers, and Strategies.",
    version="2.0.0"
)

# CORS Configuration - Critical for React 19 Frontend Integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with exact domains like ["https://smart3algo.cloud"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Modular Routers
app.include_router(auth.router)
app.include_router(brokers.router)
app.include_router(strategies.router)

import datetime

@app.get("/health", tags=["System Health"])
async def system_health_check():
    """Returns the operational status of the central trading web server."""
    return {
        "status": "operational",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
