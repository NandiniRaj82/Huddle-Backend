"""
Application configuration loaded from environment variables.

Uses python-dotenv to load .env file in development.
In production, set environment variables directly.
"""

import os
from dotenv import load_dotenv

# Load .env file if present (development)
load_dotenv()


class Settings:
    """Application settings — sourced from environment variables."""

    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_DAYS: int = int(os.environ.get("JWT_EXPIRATION_DAYS", "7"))

    def __init__(self):
        if not self.JWT_SECRET_KEY:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. "
                "Create a backend/.env file with: JWT_SECRET_KEY=<your-secret>\n"
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )


settings = Settings()
