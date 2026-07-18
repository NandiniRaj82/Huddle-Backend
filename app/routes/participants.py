"""
Participant endpoints:
  POST   /api/meetings/{code}/join               — join a meeting
  POST   /api/meetings/{code}/leave              — leave a meeting
  DELETE /api/meetings/{code}/participants/{id}   — host removes a participant
  POST   /api/meetings/{code}/participants/{id}/admit  — host admits from waiting room
  POST   /api/meetings/{code}/participants/{id}/deny   — host denies from waiting room
  GET    /api/meetings/{code}/waiting             — list waiting participants
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, col
from ..models import Meeting, Participant, JoinRequest, ParticipantResponse
from ..database import get_session

router = APIRouter(prefix="/api/meetings", tags=["participants"])


def _find_meeting(code: str, session: Session) -> Meeting:
    """Helper to find a meeting by code (with or without spaces)."""
    code_clean = code.replace(" ", "")
    formatted_code = f"{code_clean[:3]} {code_clean[3:7]} {code_clean[7:11]}" if len(code_clean) == 11 else code

    meeting = session.exec(
        select(Meeting).where(
            (Meeting.meeting_code == code) | (Meeting.meeting_code == formatted_code)
        )
    ).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


# ──────────────────────────────────────────────
# POST /api/meetings/{code}/join
# ──────────────────────────────────────────────
@router.post("/{code}/join", response_model=ParticipantResponse)
def join_meeting(code: str, data: JoinRequest, session: Session = Depends(get_session)):
    """
    Register a participant in the meeting.
    - Sets meeting status to 'active' if it was 'scheduled'.
    - Marks the participant as host if they are the meeting host.
    - If waiting_room_enabled and not the host, sets participant_status to 'waiting'.
    """
    meeting = _find_meeting(code, session)

    if meeting.status == "ended":
        raise HTTPException(status_code=400, detail="This meeting has ended")

    # Check if this user is already in the meeting (and hasn't left)
    existing = session.exec(
        select(Participant)
        .where(Participant.meeting_id == meeting.id)
        .where(Participant.user_id == data.user_id)
        .where(col(Participant.left_at) == None)
    ).first()

    if existing:
        return existing

    # Determine if this participant is the host
    is_host = (data.user_id == meeting.host_id)

    # Check participant cap (max 4 active participants)
    active_count = len(session.exec(
        select(Participant)
        .where(Participant.meeting_id == meeting.id)
        .where(col(Participant.left_at) == None)
    ).all())

    if active_count >= 4:
        raise HTTPException(status_code=400, detail="Meeting is full (max 4 participants)")

    # Determine waiting room status
    # Host always gets admitted immediately; non-host gets 'waiting' if waiting room is enabled
    participant_status = "admitted"
    if meeting.waiting_room_enabled and not is_host:
        participant_status = "waiting"

    participant = Participant(
        meeting_id=meeting.id,
        display_name=data.display_name,
        user_id=data.user_id,
        is_host=is_host,
        is_muted=False,
        participant_status=participant_status,
    )
    session.add(participant)

    # Activate the meeting if it was scheduled
    if meeting.status == "scheduled":
        meeting.status = "active"
        session.add(meeting)

    session.commit()
    session.refresh(participant)
    return participant


# ──────────────────────────────────────────────
# POST /api/meetings/{code}/leave
# ──────────────────────────────────────────────
@router.post("/{code}/leave", response_model=ParticipantResponse)
def leave_meeting(code: str, participant_id: int, session: Session = Depends(get_session)):
    """
    Mark a participant as having left the meeting.
    If no active participants remain, end the meeting.
    """
    meeting = _find_meeting(code, session)

    participant = session.get(Participant, participant_id)
    if not participant or participant.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Participant not found in this meeting")

    participant.left_at = datetime.utcnow()
    session.add(participant)

    # Check if any participants remain
    remaining = session.exec(
        select(Participant)
        .where(Participant.meeting_id == meeting.id)
        .where(col(Participant.left_at) == None)
        .where(Participant.id != participant_id)
    ).all()

    if len(remaining) == 0:
        meeting.status = "ended"
        meeting.ended_at = datetime.utcnow()
        session.add(meeting)

    session.commit()
    session.refresh(participant)
    return participant


# ──────────────────────────────────────────────
# DELETE /api/meetings/{code}/participants/{id}
# ──────────────────────────────────────────────
@router.delete("/{code}/participants/{participant_id}")
def remove_participant(
    code: str,
    participant_id: int,
    host_participant_id: int,
    session: Session = Depends(get_session),
):
    """
    Host-only: remove a participant from the meeting.
    Requires host_participant_id query param to verify host permission.
    """
    meeting = _find_meeting(code, session)

    # Verify the requester is the host
    host = session.get(Participant, host_participant_id)
    if not host or not host.is_host or host.meeting_id != meeting.id:
        raise HTTPException(status_code=403, detail="Only the host can remove participants")

    # Find and remove the target participant
    target = session.get(Participant, participant_id)
    if not target or target.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Participant not found in this meeting")

    target.left_at = datetime.utcnow()
    session.add(target)
    session.commit()

    return {"detail": f"Participant {target.display_name} removed from meeting"}


# ──────────────────────────────────────────────
# POST /api/meetings/{code}/participants/{id}/admit
# ──────────────────────────────────────────────
@router.post("/{code}/participants/{participant_id}/admit", response_model=ParticipantResponse)
def admit_participant(
    code: str,
    participant_id: int,
    session: Session = Depends(get_session),
):
    """Host-only: admit a waiting participant into the meeting."""
    meeting = _find_meeting(code, session)

    target = session.get(Participant, participant_id)
    if not target or target.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Participant not found")

    if target.participant_status != "waiting":
        raise HTTPException(status_code=400, detail="Participant is not in the waiting room")

    target.participant_status = "admitted"
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


# ──────────────────────────────────────────────
# POST /api/meetings/{code}/participants/{id}/deny
# ──────────────────────────────────────────────
@router.post("/{code}/participants/{participant_id}/deny", response_model=ParticipantResponse)
def deny_participant(
    code: str,
    participant_id: int,
    session: Session = Depends(get_session),
):
    """Host-only: deny a waiting participant — they will be redirected away."""
    meeting = _find_meeting(code, session)

    target = session.get(Participant, participant_id)
    if not target or target.meeting_id != meeting.id:
        raise HTTPException(status_code=404, detail="Participant not found")

    target.participant_status = "denied"
    target.left_at = datetime.utcnow()
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


# ──────────────────────────────────────────────
# GET /api/meetings/{code}/waiting
# ──────────────────────────────────────────────
@router.get("/{code}/waiting", response_model=list[ParticipantResponse])
def get_waiting_participants(code: str, session: Session = Depends(get_session)):
    """Get list of participants currently in the waiting room."""
    meeting = _find_meeting(code, session)

    waiting = session.exec(
        select(Participant)
        .where(Participant.meeting_id == meeting.id)
        .where(Participant.participant_status == "waiting")
        .where(col(Participant.left_at) == None)
    ).all()

    return waiting
