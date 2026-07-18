"""
Meeting history/analytics endpoints:
  GET /api/meetings/history       — list all past meetings with aggregated stats
  GET /api/meetings/history/stats — meetings-per-day for the last 7 days
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, col, func
from ..models import Meeting, Participant, User
from ..database import get_session
from ..auth import get_optional_user
from pydantic import BaseModel

router = APIRouter(prefix="/api/meetings/history", tags=["history"])


class MeetingHistoryItem(BaseModel):
    """Response schema for a single past meeting."""
    id: int
    title: str
    meeting_code: str
    meeting_type: str
    host_name: Optional[str] = None
    scheduled_start: Optional[str] = None
    created_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_minutes: int = 0
    participant_count: int = 0


class DailyStat(BaseModel):
    """Meetings per day count."""
    day: str
    count: int


# ──────────────────────────────────────────────
# GET /api/meetings/history
# ──────────────────────────────────────────────
@router.get("", response_model=list[MeetingHistoryItem])
def get_meeting_history(
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Return all meetings (ended or active) with participant counts.
    Uses authenticated user if available, otherwise defaults to user_id=1.
    """
    user_id = current_user.id if current_user else 1

    # Get all meetings hosted by this user or participated in by this user
    # Using a subquery approach
    hosted_meetings = session.exec(
        select(Meeting)
        .where(Meeting.host_id == user_id)
        .order_by(col(Meeting.created_at).desc())
    ).all()

    participated_meeting_ids = session.exec(
        select(Participant.meeting_id)
        .where(Participant.user_id == user_id)
    ).all()

    # Combine and deduplicate
    all_meeting_ids = set(m.id for m in hosted_meetings) | set(participated_meeting_ids)

    results = []
    for meeting_id in sorted(all_meeting_ids, reverse=True):
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            continue

        # Get participant count
        p_count = len(session.exec(
            select(Participant)
            .where(Participant.meeting_id == meeting.id)
        ).all())

        # Get host name
        host = session.get(User, meeting.host_id)

        # Calculate actual duration if meeting has ended
        duration = meeting.duration_minutes
        if meeting.ended_at and meeting.created_at:
            delta = meeting.ended_at - meeting.created_at
            duration = max(1, int(delta.total_seconds() / 60))

        results.append(MeetingHistoryItem(
            id=meeting.id,
            title=meeting.title,
            meeting_code=meeting.meeting_code,
            meeting_type=meeting.meeting_type,
            host_name=host.name if host else "Unknown",
            scheduled_start=meeting.scheduled_start.isoformat() if meeting.scheduled_start else None,
            created_at=meeting.created_at.isoformat() if meeting.created_at else None,
            ended_at=meeting.ended_at.isoformat() if meeting.ended_at else None,
            duration_minutes=duration,
            participant_count=p_count,
        ))

    return results


# ──────────────────────────────────────────────
# GET /api/meetings/history/stats
# ──────────────────────────────────────────────
@router.get("/stats", response_model=list[DailyStat])
def get_meeting_stats(
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Return meetings-per-day for the last 7 days.
    Used for the bar chart on the history page.
    """
    user_id = current_user.id if current_user else 1
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    # Get all meetings created in the last 7 days
    meetings = session.exec(
        select(Meeting)
        .where(Meeting.host_id == user_id)
        .where(col(Meeting.created_at) >= seven_days_ago)
    ).all()

    # Group by day
    day_counts: dict[str, int] = {}
    for i in range(7):
        day = (datetime.utcnow() - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        day_counts[day] = 0

    for meeting in meetings:
        if meeting.created_at:
            day_str = meeting.created_at.strftime("%Y-%m-%d")
            if day_str in day_counts:
                day_counts[day_str] += 1

    return [DailyStat(day=day, count=count) for day, count in day_counts.items()]
