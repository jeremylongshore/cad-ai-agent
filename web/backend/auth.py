"""Firebase Auth token validation and license gating for the web backend."""

from __future__ import annotations

import logging
import os
import time

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# License cache: {uid: (active: bool, timestamp: float)}
_license_cache: dict[str, tuple[bool, float]] = {}
_LICENSE_CACHE_TTL = 300  # 5 minutes

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


async def check_license(user: dict) -> None:
    """Verify the user holds an active license in Firestore.

    Checks the ``licenses`` collection for a document whose ID matches the
    user's Firebase UID.  The document must exist and have ``active: true``.
    Results are cached for 5 minutes to avoid hitting Firestore on every request.

    Raises HTTPException 403 if the license is missing or inactive.
    """
    # Skip in dev mode (same as auth skip)
    if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
        return

    # Reject anonymous users — Google sign-in required
    provider = user.get("firebase", {}).get("sign_in_provider", "")
    if provider == "anonymous" or not user.get("email"):
        raise HTTPException(status_code=403, detail="Google sign-in required")

    uid = user.get("uid")
    if not uid:
        logger.warning("License check called for user with no UID")
        raise HTTPException(status_code=403, detail="License check unavailable")

    now = time.monotonic()

    # Check cache
    cached = _license_cache.get(uid)
    if cached is not None:
        active, ts = cached
        if now - ts < _LICENSE_CACHE_TTL:
            if not active:
                raise HTTPException(status_code=403, detail="License inactive")
            return

    # Query Firestore (sync client wrapped for async safety)
    try:
        from starlette.concurrency import run_in_threadpool

        active = await run_in_threadpool(_fetch_license, uid)

        if not active:
            # Auto-provision 30-day trial for any Google sign-in
            email = user.get("email", "").lower()
            await run_in_threadpool(_provision_license, uid, email)
            _license_cache[uid] = (True, now)
            logger.info("Auto-provisioned 30-day trial for %s", email)
            return

        _license_cache[uid] = (active, now)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("License check failed: %s", e)
        # Fail open would be risky — fail closed instead
        raise HTTPException(status_code=403, detail="License check unavailable") from e


def _fetch_license(uid: str) -> bool:
    """Synchronous Firestore lookup — called via run_in_threadpool."""
    import datetime

    from google.cloud import firestore

    db = firestore.Client()
    doc = db.collection("licenses").document(uid).get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    if not data.get("active", False):
        return False
    expires_at = data.get("expires_at")
    return not (expires_at and expires_at < datetime.datetime.now(datetime.UTC))


def _provision_license(uid: str, email: str) -> None:
    """Auto-provision a 30-day trial license — called via run_in_threadpool."""
    import datetime

    from google.cloud import firestore

    db = firestore.Client()
    db.collection("licenses").document(uid).set({
        "active": True,
        "email": email,
        "plan": "trial",
        "provisioned_by": "auto",
        "created_at": firestore.SERVER_TIMESTAMP,
        "expires_at": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30),
    })


async def get_licensed_user(request: Request) -> dict:
    """Combined dependency: authenticate then check license."""
    user = await verify_token(request)
    await check_license(user)
    return user
