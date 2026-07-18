"""
Database engine setup and session management for SQLite via SQLModel.
The DB file lives at backend/data/zoom_clone.db.
"""

import os
from sqlmodel import SQLModel, Session, create_engine

# Database file path — stored in backend/data/ directory
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'zoom_clone.db')}"

# Create engine with check_same_thread=False for SQLite (needed for FastAPI's async)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata. Safe to call multiple times."""
    # Ensure the data directory exists
    os.makedirs(DATABASE_DIR, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    """
    FastAPI dependency that yields a database session.
    Usage: session: Session = Depends(get_session)
    """
    with Session(engine) as session:
        yield session
