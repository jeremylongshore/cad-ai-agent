"""Firebase Auth token validation, license gating, and user profile provisioning."""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    """Check if the backend is running in development mode.

    Consolidates the CAD_WEB_DEV_MODE check into a single function
    so all callers agree on which values are truthy.
    """
    return os.getenv("CAD_WEB_DEV_MODE", "").strip().lower() in ("1", "true", "yes")

# License cache: {uid: (active: bool, timestamp: float)}
_license_cache: dict[str, tuple[bool, float]] = {}
_LICENSE_CACHE_TTL = 300  # 5 minutes

# Profile cache: {uid: (profile_dict, timestamp)}
_profile_cache: dict[str, tuple[dict, float]] = {}
_PROFILE_CACHE_TTL = 300  # 5 minutes

# Tenant cache: {tenant_id: (tenant_dict, timestamp)}
_tenant_cache: dict[str, tuple[dict, float]] = {}
_TENANT_CACHE_TTL = 600  # 10 minutes — tenants rarely change

# Allowlist cache: {email: (allowed: bool, timestamp: float)}
_allowlist_cache: dict[str, tuple[bool, float]] = {}
_ALLOWLIST_CACHE_TTL = 300  # 5 minutes

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
    if is_dev_mode():
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
    if is_dev_mode():
        return

    # Reject anonymous users — Google sign-in required
    provider = user.get("firebase", {}).get("sign_in_provider", "")
    if provider == "anonymous" or not user.get("email"):
        raise HTTPException(status_code=403, detail="Sign-in required")

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
            # Open self-registration: any authenticated user gets a trial
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
    db.collection("licenses").document(uid).set(
        {
            "active": True,
            "email": email,
            "plan": "trial",
            "provisioned_by": "auto",
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30),
        }
    )


def _check_email_allowed(email: str) -> bool:
    """Check if an email is on the allowlist (env var or Firestore).

    Two sources are checked in order:
    1. ``CAD_ALLOWED_EMAILS`` env var — comma-separated list of emails
    2. Firestore ``allowlist/{email}`` document

    Results are cached for 5 minutes.  Called via ``run_in_threadpool``.
    """
    email = email.lower().strip()
    now = time.monotonic()

    cached = _allowlist_cache.get(email)
    if cached is not None:
        allowed, ts = cached
        if now - ts < _ALLOWLIST_CACHE_TTL:
            return allowed

    # 1. Check env var (fast, no network)
    # Supports both comma and semicolon separators (semicolons avoid
    # conflicts with gcloud's env var delimiter on Cloud Run deploys)
    env_list = os.getenv("CAD_ALLOWED_EMAILS", "")
    if env_list:
        raw = env_list.replace(";", ",")
        allowed_emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
        if email in allowed_emails:
            _allowlist_cache[email] = (True, now)
            return True

    # 2. Check Firestore allowlist collection
    try:
        from google.cloud import firestore

        db = firestore.Client()
        doc = db.collection("allowlist").document(email).get()
        found: bool = bool(doc.exists)
    except Exception as exc:
        logger.warning("Allowlist Firestore check failed: %s", exc)
        # Fail closed — deny access if we can't verify
        found = False

    _allowlist_cache[email] = (found, now)
    return found


# ---------------------------------------------------------------------------
# User profile + tenant auto-provisioning (EPIC-CAD-30)
# ---------------------------------------------------------------------------


async def ensure_user_profile(user: dict) -> dict:
    """Ensure the user has a profile and tenant. Returns enriched user dict.

    On first login, auto-creates a personal Tenant and UserProfile in Firestore.
    Subsequent calls hit the in-process cache (5 min TTL).
    In dev mode, returns a synthetic profile without touching Firestore.
    """
    if is_dev_mode():
        user["tenant_id"] = "dev-tenant"
        user["display_name"] = user.get("name", user.get("email", "dev"))
        return user

    uid = user.get("uid", "")
    now = time.monotonic()

    # Check profile cache
    cached = _profile_cache.get(uid)
    if cached is not None:
        profile_dict, ts = cached
        if now - ts < _PROFILE_CACHE_TTL:
            user["tenant_id"] = profile_dict["tenant_id"]
            user["display_name"] = profile_dict.get("display_name", "")
            return user

    # Firestore lookup + possible provisioning
    try:
        from starlette.concurrency import run_in_threadpool

        profile_dict = await run_in_threadpool(
            _fetch_or_create_profile,
            uid,
            user.get("email", ""),
            user.get("name", ""),
        )
        _profile_cache[uid] = (profile_dict, now)
        user["tenant_id"] = profile_dict["tenant_id"]
        user["display_name"] = profile_dict.get("display_name", "")
    except Exception as e:
        logger.warning("Profile provisioning failed (non-fatal): %s", e)
        # Fallback: use uid as tenant_id so the request can proceed
        user["tenant_id"] = uid

    return user


def _fetch_or_create_profile(uid: str, email: str, display_name: str) -> dict:
    """Sync Firestore: fetch or auto-create UserProfile + Tenant."""
    from google.cloud import firestore

    db = firestore.Client()
    profile_ref = db.collection("users").document(uid)
    profile_doc = profile_ref.get()

    if profile_doc.exists:
        data = profile_doc.to_dict()
        # Update last_login_at
        profile_ref.update({"last_login_at": datetime.now(UTC).isoformat()})
        return data

    # First login — create tenant + profile
    tenant_id = uuid.uuid4().hex[:12]
    name_part = display_name or (email.split("@")[0] if "@" in email else "") or "Personal"
    tenant_name = f"{name_part}'s Workspace"

    tenant_data = {
        "tenant_id": tenant_id,
        "name": tenant_name,
        "owner_uid": uid,
        "plan": "personal",
        "created_at": datetime.now(UTC).isoformat(),
        "settings": {},
    }
    db.collection("tenants").document(tenant_id).set(tenant_data)

    now_iso = datetime.now(UTC).isoformat()
    profile_data = {
        "uid": uid,
        "email": email,
        "display_name": display_name or email.split("@")[0],
        "company": "",
        "tenant_id": tenant_id,
        "role": "owner",
        "created_at": now_iso,
        "last_login_at": now_iso,
        "settings": {},
    }
    profile_ref.set(profile_data)

    logger.info("Auto-provisioned tenant %s + profile for %s", tenant_id, email)
    return profile_data


def _get_profile(uid: str) -> dict | None:
    """Sync Firestore lookup for user profile."""
    from google.cloud import firestore

    db = firestore.Client()
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict()
    return None


def _update_profile(uid: str, updates: dict) -> dict | None:
    """Sync Firestore update for user profile fields."""
    from google.cloud import firestore

    db = firestore.Client()
    ref = db.collection("users").document(uid)
    doc = ref.get()
    if not doc.exists:
        return None
    ref.update(updates)
    # Invalidate cache
    _profile_cache.pop(uid, None)
    return {**doc.to_dict(), **updates}


def _get_tenant(tenant_id: str) -> dict | None:
    """Sync Firestore lookup for tenant."""
    now = time.monotonic()
    cached = _tenant_cache.get(tenant_id)
    if cached is not None:
        data, ts = cached
        if now - ts < _TENANT_CACHE_TTL:
            return data

    from google.cloud import firestore

    db = firestore.Client()
    doc = db.collection("tenants").document(tenant_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    _tenant_cache[tenant_id] = (data, now)
    return data


async def get_licensed_user(request: Request) -> dict:
    """Combined dependency: authenticate, check license, ensure profile."""
    user = await verify_token(request)
    await check_license(user)
    user = await ensure_user_profile(user)
    return user
