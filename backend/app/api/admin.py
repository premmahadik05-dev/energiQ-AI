from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import AuditEvent, Dataset, Job, ModelVersion, Notification, User
from ..schemas import AuditOut, NotificationOut, UserOut, UserPatch
from ..security import current_user_dep, require_roles
from ..services.core import job_counts
from .deps import audit, get_session, ip_of

router = APIRouter(tags=["admin and notifications"])
ADMIN = require_roles("admin")


@router.get("/admin/users", response_model=list[UserOut])
def users(user: User = Depends(ADMIN), db: Session = Depends(get_session)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, body: UserPatch, request: Request, admin: User = Depends(ADMIN), db: Session = Depends(get_session)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if target.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(400, "You cannot demote or deactivate your own account")
    changes = {}
    if body.role is not None and body.role != target.role:
        changes["role"] = [target.role, body.role]
        target.role = body.role
    if body.is_active is not None and body.is_active != target.is_active:
        changes["is_active"] = [target.is_active, body.is_active]
        target.is_active = body.is_active
    db.commit()
    if changes:
        audit(db, admin.id, "admin_user_change", ip_of(request), "user", target.id, changes)
    return target


@router.get("/admin/audit", response_model=list[AuditOut])
def audit_log(limit: int = Query(100, ge=1, le=500), action: str | None = Query(None, max_length=40),
              admin: User = Depends(ADMIN), db: Session = Depends(get_session)):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if action:
        q = q.where(AuditEvent.action == action)
    return db.scalars(q).all()


@router.get("/admin/system")
def system(request: Request, admin: User = Depends(ADMIN), db: Session = Depends(get_session)):
    counts = {name: db.scalar(select(func.count()).select_from(m)) for name, m in
              (("users", User), ("datasets", Dataset), ("models", ModelVersion), ("jobs", Job))}
    return {"counts": counts, "jobs_by_status": job_counts(request.app.state.db), "http": request.app.state.metrics.summary(),
            "environment": request.app.state.settings.env}


# ----------------------------------------------------------------------------- notifications (any signed-in user)
@router.get("/notifications", response_model=list[NotificationOut])
def notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=100), user: User = Depends(current_user_dep),
                  db: Session = Depends(get_session)):
    q = select(Notification).where(Notification.owner_id == user.id).order_by(Notification.id.desc()).limit(limit)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    return db.scalars(q).all()


@router.post("/notifications/read-all", status_code=204)
def read_all(user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    db.execute(update(Notification).where(Notification.owner_id == user.id).values(is_read=True))
    db.commit()


@router.post("/notifications/{nid}/read", response_model=NotificationOut)
def read_one(nid: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    n = db.scalar(select(Notification).where(Notification.id == nid, Notification.owner_id == user.id))
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return n
