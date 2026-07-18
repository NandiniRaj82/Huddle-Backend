"""
FastAPI application entry point.

Configures:
- CORS middleware for frontend (localhost:3000)
- Database initialization and seeding on startup
- Meeting, participant, and WebSocket signaling routes
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import create_db_and_tables
from .seed import seed_database
from .routes.meetings import router as meetings_router
from .routes.participants import router as participants_router
from .routes.auth import router as auth_router
from .routes.history import router as history_router
from .ws.signaling import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed the database."""
    create_db_and_tables()
    seed_database()
    yield


app = FastAPI(
    title="Zoom Clone API",
    description="Backend API for the Zoom Web App clone — meetings, participants, and WebRTC signaling.",
    version="1.0.0",
    lifespan=lifespan,
)

# Get frontend URL from env or fallback to localhost
import os
from dotenv import load_dotenv
load_dotenv()

frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
origins = []
for url in frontend_url.split(","):
    cleaned = url.strip().rstrip("/")
    if cleaned:
        origins.append(cleaned)

# Always ensure localhost:3000 is allowed
if "http://localhost:3000" not in origins:
    origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.(devtunnels\.ms|ngrok-free\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register route modules ──
app.include_router(auth_router)
app.include_router(history_router)  # Must be before meetings_router (path conflict: /history vs /{code})
app.include_router(meetings_router)
app.include_router(participants_router)
app.include_router(ws_router)


@app.get("/")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "zoom-clone-api"}
