"""
SQLModel ORM models matching the exact database schema spec.
Three tables: users, meetings, participants.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship


# ──────────────────────────────────────────────
# Database Models (SQLModel = SQLAlchemy + Pydantic)
# ──────────────────────────────────────────────

class User(SQLModel, table=True):
    """Represents a registered user. Single seeded user 'Alex Morgan' is used everywhere."""
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    email: str = Field(nullable=False, unique=True)
    password_hash: Optional[str] = Field(default=None)  # NULL for legacy seeded users
    avatar_color: str = Field(default="#0B5CFF")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    # Relationships
    hosted_meetings: list["Meeting"] = Relationship(back_populates="host")
    participations: list["Participant"] = Relationship(back_populates="user")


class Meeting(SQLModel, table=True):
    """
    Represents a meeting — either 'instant' or 'scheduled'.
    meeting_code is Zoom-style: 11 digits formatted 'XXX XXXX XXXX'.
    """
    __tablename__ = "meetings"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_code: str = Field(nullable=False, unique=True, index=True)
    host_id: int = Field(foreign_key="users.id", nullable=False)
    title: str = Field(default="New Meeting", nullable=False)
    description: Optional[str] = None
    meeting_type: str = Field(nullable=False)  # 'instant' or 'scheduled'
    scheduled_start: Optional[datetime] = None
    duration_minutes: int = Field(default=30)
    status: str = Field(default="scheduled", nullable=False)  # 'scheduled', 'active', 'ended'
    waiting_room_enabled: bool = Field(default=True)  # Whether participants must wait for host admission
    invite_link: str = Field(nullable=False)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    # Relationships
    host: Optional[User] = Relationship(back_populates="hosted_meetings")
    participants: list["Participant"] = Relationship(back_populates="meeting")


class Participant(SQLModel, table=True):
    """
    Tracks who joined a meeting and when.
    - left_at being set means the participant has left (used for 'recent meetings' queries).
    - is_host controls permission for mute-all/kick actions.
    """
    __tablename__ = "participants"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", nullable=False, index=True)
    display_name: str = Field(nullable=False)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    is_host: bool = Field(default=False)
    joined_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    left_at: Optional[datetime] = None
    is_muted: bool = Field(default=False)
    participant_status: str = Field(default="admitted")  # 'waiting', 'admitted', 'denied'

    # Relationships
    meeting: Optional[Meeting] = Relationship(back_populates="participants")
    user: Optional[User] = Relationship(back_populates="participations")


# ──────────────────────────────────────────────
# Pydantic Request / Response Schemas
# ──────────────────────────────────────────────

class MeetingCreate(SQLModel):
    """Request body for scheduling a meeting."""
    title: str = "New Meeting"
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    duration_minutes: int = 30


class MeetingResponse(SQLModel):
    """Response schema for meeting data."""
    id: int
    meeting_code: str
    host_id: int
    title: str
    description: Optional[str]
    meeting_type: str
    scheduled_start: Optional[datetime]
    duration_minutes: int
    status: str
    waiting_room_enabled: bool = True
    invite_link: str
    created_at: Optional[datetime]
    ended_at: Optional[datetime]


class ParticipantResponse(SQLModel):
    """Response schema for participant data."""
    id: int
    meeting_id: int
    display_name: str
    user_id: Optional[int]
    is_host: bool
    joined_at: Optional[datetime]
    left_at: Optional[datetime]
    is_muted: bool
    participant_status: str = "admitted"


class JoinRequest(SQLModel):
    """Request body for joining a meeting."""
    display_name: str
    user_id: Optional[int] = 1  # Default to seeded user


class MeetingWithHost(SQLModel):
    """Meeting response with host name included."""
    id: int
    meeting_code: str
    host_id: int
    host_name: Optional[str] = None
    title: str
    description: Optional[str]
    meeting_type: str
    scheduled_start: Optional[datetime]
    duration_minutes: int
    status: str
    waiting_room_enabled: bool = True
    invite_link: str
    created_at: Optional[datetime]
    ended_at: Optional[datetime]
    participant_count: int = 0


# ──────────────────────────────────────────────
# Auth Schemas
# ──────────────────────────────────────────────

class AuthSignup(SQLModel):
    """Request body for user registration."""
    name: str
    email: str
    password: str


class AuthLogin(SQLModel):
    """Request body for user login."""
    email: str
    password: str


class AuthResponse(SQLModel):
    """Response body for auth endpoints — returns JWT token + user info."""
    token: str
    user: "UserResponse"


class UserResponse(SQLModel):
    """Public user info returned by /api/auth/me and in auth responses."""
    id: int
    name: str
    email: str
    avatar_color: str
    created_at: Optional[datetime]
