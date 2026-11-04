from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, utcnow
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import (
    EMAIL_RE,
    burn_password_time,
    create_access_token,
    current_user_dep,
    enforce,
    hash_password,
    validate_password,
    verify_password,
)
from .deps import audit, get_session, ip_of, settings_of

router = APIRouter(prefix="/auth", tags=["auth"])


def _norm_email(e: str) -> str:
    e = e.strip().lower()
    if not EMAIL_RE.match(e):
        raise HTTPException(422, "Enter a valid e-mail address")
    return e


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_session)):
    s = settings_of(request)
    if not s.allow_registration:
        raise HTTPException(403, "Registration is disabled")
    ip = ip_of(request)
    enforce(request.app.state.limiter, f"register:{ip}", s.register_per_hour, 3600)
    email = _norm_email(body.email)
    validate_password(body.password)
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "That e-mail is already registered")
    user = User(email=email, full_name=body.full_name.strip()[:120], password_hash=hash_password(body.password), role="analyst")
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user.id, "register", ip, "user", user.id)
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_session)):
    s = settings_of(request)
    ip = ip_of(request)
    email = body.email.strip().lower()
    lim = request.app.state.limiter
    enforce(lim, f"login:{ip}", s.login_per_minute, 60)
    enforce(lim, f"login:{ip}:{email}", 5, 300)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_password_time(body.password)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, user.id if user else None, "login_failed", ip, "user", user.id if user else "", {"email": email[:100]})
        raise HTTPException(401, "Invalid e-mail or password", headers={"WWW-Authenticate": "Bearer"})
    user.last_login_at = utcnow()
    db.commit()
    audit(db, user.id, "login", ip, "user", user.id)
    token, ttl = create_access_token(s, user)
    return TokenOut(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user_dep)):
    return user
