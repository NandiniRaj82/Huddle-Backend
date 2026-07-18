"""
Auth API endpoints:
  POST /api/auth/signup  — register a new user
  POST /api/auth/login   — authenticate and get JWT
  GET  /api/auth/me      — get current user info from JWT
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..models import User, AuthSignup, AuthLogin, AuthResponse, UserResponse
from ..database import get_session
from ..auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    """Convert a User ORM model to a UserResponse schema."""
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_color=user.avatar_color,
        created_at=user.created_at,
    )


# ──────────────────────────────────────────────
# POST /api/auth/signup
# ──────────────────────────────────────────────
@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(data: AuthSignup, session: Session = Depends(get_session)):
    """Register a new user with name, email, and password."""
    # Validate input
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not data.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check if email already exists
    existing = session.exec(select(User).where(User.email == data.email.strip().lower())).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Create user
    user = User(
        name=data.name.strip(),
        email=data.email.strip().lower(),
        password_hash=hash_password(data.password),
        avatar_color=_generate_avatar_color(data.name),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Generate JWT
    token = create_access_token(user.id, user.name, user.email)
    return AuthResponse(token=token, user=_user_response(user))


# ──────────────────────────────────────────────
# POST /api/auth/login
# ──────────────────────────────────────────────
@router.post("/login", response_model=AuthResponse)
def login(data: AuthLogin, session: Session = Depends(get_session)):
    """Authenticate with email and password, returns JWT."""
    user = session.exec(select(User).where(User.email == data.email.strip().lower())).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.name, user.email)
    return AuthResponse(token=token, user=_user_response(user))


# ──────────────────────────────────────────────
# GET /api/auth/me
# ──────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile. Requires valid JWT."""
    return _user_response(current_user)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

# Deterministic avatar colors — same palette as the frontend
_AVATAR_COLORS = [
    "#0B5CFF",  # Blue (Zoom primary)
    "#7B61FF",  # Purple
    "#00A67E",  # Green
    "#F76B1C",  # Orange
    "#E5484D",  # Red
    "#0EA5E9",  # Sky blue
    "#D946EF",  # Fuchsia
    "#059669",  # Emerald
]


def _generate_avatar_color(name: str) -> str:
    """Generate a deterministic avatar color from a name."""
    hash_val = sum(ord(c) for c in name)
    return _AVATAR_COLORS[hash_val % len(_AVATAR_COLORS)]
