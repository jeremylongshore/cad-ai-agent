#!/usr/bin/env python3
"""Manually provision a beta license for a user by email.

Usage:
    python scripts/provision_beta_user.py user@example.com

Looks up the Firebase UID by email and creates a ``licenses/{uid}`` Firestore
document with ``active: true``.  Requires Application Default Credentials with
access to the ``cad-dxf-agent`` project.
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print(f"Usage: {sys.argv[0]} user@example.com")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    import firebase_admin
    from firebase_admin import auth, credentials
    from google.cloud import firestore

    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"projectId": "cad-dxf-agent"})

    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        print(f"No Firebase user found for {email}")
        sys.exit(1)

    uid = user.uid
    db = firestore.Client(project="cad-dxf-agent")
    doc_ref = db.collection("licenses").document(uid)

    existing = doc_ref.get()
    if existing.exists and existing.to_dict().get("active"):
        print(f"License already active for {email} (uid={uid})")
        return

    doc_ref.set({
        "active": True,
        "email": email,
        "provisioned_by": "manual",
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    print(f"License provisioned for {email} (uid={uid})")


if __name__ == "__main__":
    main()
