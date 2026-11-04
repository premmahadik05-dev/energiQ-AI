"""Password hashing (argon2id), JWT access tokens, rate limiting and authorisation dependencies."""
from __future__ import annotations

import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import User

_hasher = PasswordHasher()  # argon2id with library defaults
ALGORITHM = "HS256"
ROLES = ("admin", "analyst", "viewer")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
COMMON_PASSWORDS = {"password123", "1234567890", "qwertyuiop", "password1234", "letmein1234", "admin12345"}


def validate_password(pw: str) -> None:
    if len(pw) < 10 or len(pw) > 128:
        raise HTTPException(422, "Password must be 10-128 characters")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise HTTPException(422, "Password must contain letters and digits")
    if pw.lower() in COMMON_PASSWORDS or len(set(pw)) < 5:
        raise HTTPException(422, "Password is too easy to guess")


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing")


def burn_password_time(pw: str) -> None:
    """Spend the same time as a real verification so unknown e-mails are not distinguishable by latency."""
    verify_password(pw, _DUMMY_HASH)


def create_access_token(settings: Settings, user: User) -> tuple[str, int]:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "role": user.role, "iat": now, "exp": exp, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), settings.access_token_minutes * 60


def decode_token(settings: Settings, token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})


# ----------------------------------------------------------------------------- rate limiting
class RateLimiter:
    """In-process sliding-window limiter. Per-process by design; behind several workers use a shared store."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float) -> float | None:
        """Record a hit; return seconds to wait if the limit is exceeded, else None."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, window_s - (now - q[0]))
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request, trust_proxy: bool, hops: int = 1) -> str:
    """Best-effort client address for rate limiting and audit.

    Behind ``hops`` trusted reverse proxies that each *append* the address they saw to X-Forwarded-For, the real client
    is the entry ``hops`` places from the right. Anything further left was supplied by the client and is ignored, so a
    forged header cannot be used to dodge per-IP limits. With ``trust_proxy`` off the header is ignored completely.
    """
    if trust_proxy:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
        if len(entries) >= max(1, hops):
            return entries[-max(1, hops)][:64]
    return (request.client.host if request.client else "unknown")[:64]


def enforce(limiter: RateLimiter, key: str, limit: int, window_s: float) -> None:
    wait = limiter.hit(key, limit, window_s)
    if wait is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down",
                            headers={"Retry-After": str(int(wait))})


# ----------------------------------------------------------------------------- dependencies
_bearer = HTTPBearer(auto_error=False)


def current_user_dep(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    app_state = request.app.state
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_token(app_state.settings, creds.credentials)
        uid = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized from None
    with app_state.db.session() as db:
        user = db.scalar(select(User).where(User.id == uid))
        if user is None or not user.is_active:
            raise unauthorized
        db.expunge(user)
    request.state.user_id = user.id
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user_dep)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not allow this action")
        return user

    dep.allowed_roles = roles  # introspected by scripts/make_api_reference.py and the security tests
    return dep


def get_session(request: Request):
    s: Session = request.app.state.db.session()
    try:
        yield s
    finally:
        s.close()
