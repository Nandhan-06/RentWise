"""
auth.py — RentWise Module 7 (Auth)

Session-cookie auth, not JWT — deliberately. This stack is server-rendered
Jinja + vanilla JS, not a token-consuming SPA, so a signed session cookie
(via Starlette's SessionMiddleware, added in app.py) is the proportionate
choice: no refresh-token rotation, no client-side token storage, no extra
attack surface those bring. The cookie is set httponly + samesite=lax,
which is why every browser fetch() call in this project's JS can just
work without ever touching a token — the browser sends the cookie
automatically on same-origin requests.

Password hashing uses Argon2id (via argon2-cffi), the modern default
recommended over bcrypt: memory-hard (harder to brute-force on GPUs than
bcrypt), no 72-byte input truncation quirk, and PasswordHasher.hash()
already encodes its own parameters into the stored string, so there's
nothing extra to track as defaults change over time.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request

import database as db

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerificationError, InvalidHashError):
        return False


def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency for endpoints that REQUIRE login. Raises 401 if no
    valid session exists. Deliberately returns the full safe user dict
    (never the hash — see database.get_user, which already excludes it)
    so route handlers get user_id, name, email, phone, role in one call.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = db.get_user(user_id)
    if not user:
        # Session refers to a user that no longer exists — clear it rather
        # than raise something confusing.
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not logged in")

    return user


def get_current_user_optional(request: Request) -> dict | None:
    """
    For pages/endpoints that behave differently for guests vs. logged-in
    users but don't require login outright — e.g. every page route, so
    the nav bar can show 'Login' vs. the user's name.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get_user(user_id)
