"""Firebase Auth token validation for the web backend."""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Lazy-init firebase admin
_firebase_app = None


def _init_firebase():
    global _firebase_app
    if _firebase_app is not None:
        return

    import firebase_admin
    from firebase_admin import credentials

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    else:
        # Uses ADC (Application Default Credentials) on Cloud Run
        _firebase_app = firebase_admin.initialize_app()


async def verify_token(request: Request) -> dict:
    """Extract and verify Firebase ID token from Authorization header.

    Returns the decoded token dict with uid, email, etc.
    Raises HTTPException 401 if missing or invalid.
    """
    # Skip auth in development mode
    if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
        return {"uid": "dev-user", "email": "dev@localhost"}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    try:
        _init_firebase()
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        logger.warning("Token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e
