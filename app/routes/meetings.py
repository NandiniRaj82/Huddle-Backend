"""
Meeting CRUD endpoints:
  POST   /api/meetings/instant    — create an instant meeting
  POST   /api/meetings/schedule   — create a scheduled meeting
  GET    /api/meetings/upcoming   — list upcoming scheduled meetings
  GET    /api/meetings/recent     — list recent (ended) meetings
  GET    /api/meetings/{code}     — get a single meeting by code
"""

import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, col
from ..models import Meeting, MeetingCreate, MeetingResponse, MeetingWithHost, User, Participant
from ..database import get_session
from ..seed import generate_meeting_code
from ..auth import get_optional_user

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


# ──────────────────────────────────────────────
# POST /api/meetings/instant
# ──────────────────────────────────────────────
@router.post("/instant", response_model=MeetingResponse)
def create_instant_meeting(
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Create an instant meeting — immediately active, ready to join."""
    host_id = current_user.id if current_user else 1  # Fall back to seeded default user
    code = generate_meeting_code()
    code_no_spaces = code.replace(" ", "")

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    meeting = Meeting(
        meeting_code=code,
        host_id=host_id,
        title="New Meeting",
        meeting_type="instant",
        status="active",
        invite_link=f"{frontend_url}/meeting/{code_no_spaces}",
    )
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


# ──────────────────────────────────────────────
# POST /api/meetings/schedule
# ──────────────────────────────────────────────
@router.post("/schedule", response_model=MeetingResponse)
def schedule_meeting(
    data: MeetingCreate,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Create a scheduled meeting with title, description, start time, and duration."""
    host_id = current_user.id if current_user else 1  # Fall back to seeded default user
    code = generate_meeting_code()
    code_no_spaces = code.replace(" ", "")

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    meeting = Meeting(
        meeting_code=code,
        host_id=host_id,
        title=data.title,
        description=data.description,
        meeting_type="scheduled",
        scheduled_start=data.scheduled_start,
        duration_minutes=data.duration_minutes,
        status="scheduled",
        invite_link=f"{frontend_url}/meeting/{code_no_spaces}",
    )
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


# ──────────────────────────────────────────────
# GET /api/meetings/upcoming
# ──────────────────────────────────────────────
@router.get("/upcoming", response_model=list[MeetingWithHost])
def get_upcoming_meetings(
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Return scheduled meetings where scheduled_start is in the future.
    Used for the 'Upcoming Meetings' section on the dashboard.
    """
    user_id = current_user.id if current_user else 1
    now = datetime.utcnow()
    statement = (
        select(Meeting)
        .where(Meeting.status == "scheduled")
        .where(col(Meeting.scheduled_start) > now)
        .where(Meeting.host_id == user_id)
        .order_by(col(Meeting.scheduled_start).asc())
    )
    meetings = session.exec(statement).all()

    results = []
    for m in meetings:
        # Get participant count for active participants
        participants = session.exec(
            select(Participant)
            .where(Participant.meeting_id == m.id)
            .where(col(Participant.left_at) == None)
        ).all()

        # Get host name
        host = session.get(User, m.host_id)

        results.append(MeetingWithHost(
            id=m.id,
            meeting_code=m.meeting_code,
            host_id=m.host_id,
            host_name=host.name if host else None,
            title=m.title,
            description=m.description,
            meeting_type=m.meeting_type,
            scheduled_start=m.scheduled_start,
            duration_minutes=m.duration_minutes,
            status=m.status,
            waiting_room_enabled=m.waiting_room_enabled,
            invite_link=m.invite_link,
            created_at=m.created_at,
            ended_at=m.ended_at,
            participant_count=len(participants),
        ))
    return results


# ──────────────────────────────────────────────
# GET /api/meetings/recent
# ──────────────────────────────────────────────
@router.get("/recent", response_model=list[MeetingWithHost])
def get_recent_meetings(
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Return meetings that the user has participated in and left.
    These have participant rows with left_at set.
    Used for the 'Recent Meetings' section on the dashboard.
    """
    user_id = current_user.id if current_user else 1
    # Find meetings where the user has a participant record with left_at set
    statement = (
        select(Meeting)
        .join(Participant, Participant.meeting_id == Meeting.id)
        .where(col(Participant.left_at) != None)
        .where(Participant.user_id == user_id)
        .order_by(col(Participant.left_at).desc())
    )
    meetings = session.exec(statement).all()

    results = []
    seen_ids = set()  # Avoid duplicates if user joined multiple times
    for m in meetings:
        if m.id in seen_ids:
            continue
        seen_ids.add(m.id)

        host = session.get(User, m.host_id)
        results.append(MeetingWithHost(
            id=m.id,
            meeting_code=m.meeting_code,
            host_id=m.host_id,
            host_name=host.name if host else None,
            title=m.title,
            description=m.description,
            meeting_type=m.meeting_type,
            scheduled_start=m.scheduled_start,
            duration_minutes=m.duration_minutes,
            status=m.status,
            waiting_room_enabled=m.waiting_room_enabled,
            invite_link=m.invite_link,
            created_at=m.created_at,
            ended_at=m.ended_at,
            participant_count=0,
        ))
    return results


# ──────────────────────────────────────────────
# GET /api/meetings/{code}
# ──────────────────────────────────────────────
@router.get("/{code}", response_model=MeetingWithHost)
def get_meeting(code: str, session: Session = Depends(get_session)):
    """
    Get a single meeting by its code. Accepts codes with or without spaces.
    Returns 404 if not found.
    """
    # Normalize: try both with and without spaces
    code_clean = code.replace(" ", "")
    formatted_code = f"{code_clean[:3]} {code_clean[3:7]} {code_clean[7:11]}" if len(code_clean) == 11 else code

    meeting = session.exec(
        select(Meeting).where(
            (Meeting.meeting_code == code) | (Meeting.meeting_code == formatted_code)
        )
    ).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get active participant count
    participants = session.exec(
        select(Participant)
        .where(Participant.meeting_id == meeting.id)
        .where(col(Participant.left_at) == None)
    ).all()

    host = session.get(User, meeting.host_id)

    return MeetingWithHost(
        id=meeting.id,
        meeting_code=meeting.meeting_code,
        host_id=meeting.host_id,
        host_name=host.name if host else None,
        title=meeting.title,
        description=meeting.description,
        meeting_type=meeting.meeting_type,
        scheduled_start=meeting.scheduled_start,
        duration_minutes=meeting.duration_minutes,
        status=meeting.status,
        waiting_room_enabled=meeting.waiting_room_enabled,
        invite_link=meeting.invite_link,
        created_at=meeting.created_at,
        ended_at=meeting.ended_at,
        participant_count=len(participants),
    )
