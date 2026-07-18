"""
Seed script — populates the database with:
- 1 default user: Alex Morgan
- 3 upcoming scheduled meetings (next 7 days)
- 2 recent/past meetings with participant rows that have left_at set
"""

import random
import os
from datetime import datetime, timedelta
from sqlmodel import Session, select
from .models import User, Meeting, Participant
from .database import engine


def generate_meeting_code() -> str:
    """Generate a Zoom-style meeting code: 11 digits formatted as 'XXX XXXX XXXX'."""
    digits = ''.join([str(random.randint(0, 9)) for _ in range(11)])
    return f"{digits[:3]} {digits[3:7]} {digits[7:11]}"


from .auth import hash_password

def seed_database():
    """
    Seed the database with initial data. Only runs if no users exist yet
    (prevents duplicate seeding on restart).
    """
    with Session(engine) as session:
        # Check if already seeded
        existing_user = session.exec(select(User)).first()
        if existing_user:
            print("Database already seeded, skipping.")
            return

        print("Seeding database...")

        # ── 1. Create default user ──
        default_user = User(
            name="Alex Morgan",
            email="alex.morgan@example.com",
            password_hash=hash_password("password123"),
            avatar_color="#0B5CFF"
        )
        session.add(default_user)
        session.commit()
        session.refresh(default_user)
        print(f"  Created user: {default_user.name} (id={default_user.id})")

        now = datetime.utcnow()

        # ── 2. Create 3 upcoming scheduled meetings ──
        upcoming_meetings = [
            {
                "title": "Q3 Planning Review",
                "description": "Review quarterly goals and align on deliverables for Q3.",
                "scheduled_start": now + timedelta(days=1, hours=2),
                "duration_minutes": 60,
            },
            {
                "title": "Design Sprint Kickoff",
                "description": "Kick off the new design sprint for the mobile app redesign.",
                "scheduled_start": now + timedelta(days=3, hours=4),
                "duration_minutes": 45,
            },
            {
                "title": "Weekly Team Standup",
                "description": "Regular weekly sync to discuss progress and blockers.",
                "scheduled_start": now + timedelta(days=5, hours=1),
                "duration_minutes": 30,
            },
        ]

        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
        for meeting_data in upcoming_meetings:
            code = generate_meeting_code()
            code_no_spaces = code.replace(" ", "")
            meeting = Meeting(
                meeting_code=code,
                host_id=default_user.id,
                title=meeting_data["title"],
                description=meeting_data["description"],
                meeting_type="scheduled",
                scheduled_start=meeting_data["scheduled_start"],
                duration_minutes=meeting_data["duration_minutes"],
                status="scheduled",
                invite_link=f"{frontend_url}/meeting/{code_no_spaces}",
            )
            session.add(meeting)
            session.commit()
            session.refresh(meeting)
            print(f"  Created upcoming meeting: {meeting.title} ({meeting.meeting_code})")

        # ── 3. Create 2 recent/past meetings (ended, with participant records) ──
        past_meetings = [
            {
                "title": "Product Roadmap Sync",
                "description": "Discussed product roadmap priorities for the next quarter.",
                "scheduled_start": now - timedelta(days=2, hours=3),
                "duration_minutes": 45,
                "ended_offset": timedelta(days=2, hours=2, minutes=15),
            },
            {
                "title": "Client Onboarding Call",
                "description": "Walked through the onboarding process with the new client team.",
                "scheduled_start": now - timedelta(days=1, hours=5),
                "duration_minutes": 30,
                "ended_offset": timedelta(days=1, hours=4, minutes=30),
            },
        ]

        for meeting_data in past_meetings:
            code = generate_meeting_code()
            code_no_spaces = code.replace(" ", "")
            ended_at = now - meeting_data["ended_offset"]

            meeting = Meeting(
                meeting_code=code,
                host_id=default_user.id,
                title=meeting_data["title"],
                description=meeting_data["description"],
                meeting_type="scheduled",
                scheduled_start=meeting_data["scheduled_start"],
                duration_minutes=meeting_data["duration_minutes"],
                status="ended",
                invite_link=f"{frontend_url}/meeting/{code_no_spaces}",
                ended_at=ended_at,
            )
            session.add(meeting)
            session.commit()
            session.refresh(meeting)

            # Add participant record with left_at set (makes it a "recent" meeting)
            participant = Participant(
                meeting_id=meeting.id,
                display_name=default_user.name,
                user_id=default_user.id,
                is_host=True,
                joined_at=meeting_data["scheduled_start"],
                left_at=ended_at,
            )
            session.add(participant)
            session.commit()
            print(f"  Created past meeting: {meeting.title} ({meeting.meeting_code})")

        print("Database seeding complete!")
