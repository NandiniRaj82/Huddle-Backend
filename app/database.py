"""
Database engine setup and session management for SQLite via SQLModel.
The DB file lives at backend/data/zoom_clone.db.
"""

import os
from sqlmodel import SQLModel, Session, create_engine

db_url_from_env = os.environ.get("DATABASE_URL")
if db_url_from_env:
    DATABASE_URL = db_url_from_env
else:
    DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'zoom_clone.db')}"

# Create engine with check_same_thread=False only for SQLite
is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args
)


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata. Safe to call multiple times."""
    if is_sqlite:
        DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(DATABASE_DIR, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    """
    FastAPI dependency that yields a database session.
    Usage: session: Session = Depends(get_session)
    """
    with Session(engine) as session:
        yield session
