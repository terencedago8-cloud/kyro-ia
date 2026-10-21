"""Administration KYRO AI — toutes les routes sont protégées par `require_admin` (rôle relu en base).

Règles de sécurité appliquées ici :
- Un administrateur ne peut ni modifier son propre rôle, ni se suspendre, ni se supprimer.
- Impossible de supprimer ou rétrograder le dernier administrateur.
- Toute opération de crédits exige une raison et est journalisée (credit_ledger + admin_logs).
- Les clés API ne sont JAMAIS renvoyées au navigateur (masquées).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import credits as credit_service
from .. import schemas
from ..database import get_db
from ..deps import require_admin
from ..services import ai
from ..models import (
    AdminLog,
    AuditLog,
    CreditLedger,
    Generation,
    LoginAttempt,
    User,
    UserCredit,
    utcnow,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- Statistiques ----------

@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    now = utcnow()
    day_ago = now - timedelta(hours=24)

    total_users = db.execute(select(func.count()).select_from(User)).scalar() or 0
    active_users = db.execute(
        select(func.count()).select_from(User).where(User.last_login >= day_ago)
    ).scalar() or 0

    def count_generations(kind: str | None = None, status_: str | None = None) -> int:
        q = select(func.count()).select_from(Generation)
        if kind:
            q = q.where(Generation.kind == kind)
        if status_:
            q = q.where(Generation.status == status_)
        return db.execute(q).scalar() or 0

    return {
        "total_users": total_users,
        "active_users_24h": active_users,
        "images": count_generations("IMAGE"),
        "videos": count_generations("VIDEO"),
        "chat_requests": count_generations("CHAT"),
        "code_requests": count_generations("CODE"),
        "failed_generations": count_generations(status_="FAILED"),
        "generations_24h": db.execute(
            select(func.count()).select_from(Generation).where(Generation.created_at >= day_ago)
        ).scalar() or 0,
        "credits_consumed_total": credit_service.count_consumed(db),
        "credits_consumed_24h": credit_service.count_consumed(db, since=day_ago),
    }


# ---------- Utilisateurs ----------

@router.get("/users")
def list_users(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Liste + recherche par pseudo ou e-mail, avec solde et dernière connexion."""
    q = select(User)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(User.username.ilike(like), User.email.ilike(like)))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    users = db.execute(q.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()

    items = []
    for u in users:
        credit = db.get(UserCredit, u.id)
        last_gen = db.execute(
            select(Generation).where(Generation.user_id == u.id).order_by(Generation.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        items.append({
            "id": u.id, "email": u.email, "username": u.username, "role": u.role,
            "is_suspended": u.is_suspended,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "credits": credit.balance if credit else 0,
            "last_activity": last_gen.created_at.isoformat() if last_gen else None,
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: Session = Depends(get_db)):
    """Fiche complète : profil, connexions récentes, dernières générations, historique de crédits."""
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    credit = db.get(UserCredit, u.id)
    logins = db.execute(
        select(LoginAttempt).where(LoginAttempt.email == u.email).order_by(LoginAttempt.created_at.desc()).limit(10)
    ).scalars().all()
    generations = db.execute(
        select(Generation).where(Generation.user_id == u.id).order_by(Generation.created_at.desc()).limit(25)
    ).scalars().all()
    ledger = db.execute(
        select(CreditLedger).where(CreditLedger.user_id == u.id).order_by(CreditLedger.created_at.desc()).limit(25)
    ).scalars().all()
    return {
        "user": schemas.UserOut.from_user(u),
        "credits": {"balance": credit.balance if credit else 0, "period_start": credit.period_start.isoformat() if credit else None},
        "logins": [{"ip": l.ip, "success": l.success, "created_at": l.created_at.isoformat()} for l in logins],
        "generations": [schemas.GenerationOut.from_gen(g) for g in generations],
        "credit_history": [
            {"delta": r.delta, "balance_after": r.balance_after, "kind": r.kind, "reason": r.reason, "created_at": r.created_at.isoformat()}
            for r in ledger
        ],
    }


@router.patch("/users/{user_id}")
def patch_user(payload: schemas.AdminUserPatch, user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Modifier le rôle, suspendre ou réactiver un compte (interdit sur soi-même)."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vous ne pouvez pas modifier votre propre compte ici.")
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")

    if payload.role is not None and payload.role != u.role:
        if payload.role == "USER":
            admins = db.execute(select(func.count()).select_from(User).where(User.role == "ADMIN")).scalar() or 0
            if admins <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impossible de rétrograder le dernier administrateur.")
        u.role = payload.role
        db.add(AdminLog(actor_id=admin.id, action="ROLE_CHANGED", target_user_id=u.id, details={"role": payload.role}))

    if payload.is_suspended is not None:
        u.is_suspended = payload.is_suspended
        db.add(AdminLog(
            actor_id=admin.id, action="USER_SUSPENDED" if payload.is_suspended else "USER_REACTIVATED",
            target_user_id=u.id, details={"by": admin.username},
        ))
    db.commit()
    return {"user": schemas.UserOut.from_user(u)}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Suppression sécurisée : cascades SQL (crédits, générations, conversations)."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vous ne pouvez pas supprimer votre propre compte.")
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    if u.role == "ADMIN":
        admins = db.execute(select(func.count()).select_from(User).where(User.role == "ADMIN")).scalar() or 0
        if admins <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impossible de supprimer le dernier administrateur.")
    db.add(AdminLog(actor_id=admin.id, action="USER_DELETED", target_user_id=u.id, details={"email": u.email, "username": u.username}))
    db.delete(u)
    db.commit()


# ---------- Crédits ----------

@router.post("/users/{user_id}/credits")
def adjust_credits(payload: schemas.AdminCreditIn, user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Ajouter / retirer / définir / réinitialiser les crédits — raison obligatoire, tout est journalisé."""
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    try:
        credit = credit_service.admin_adjust_credits(db, admin.id, user_id, payload.action, payload.amount, payload.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"user_id": user_id, "balance": credit.balance}


@router.get("/users/{user_id}/credits/history")
def credits_history(user_id: str, db: Session = Depends(get_db), page: int = 1, page_size: int = 50):
    q = select(CreditLedger).where(CreditLedger.user_id == user_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(q.order_by(CreditLedger.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "total": total,
        "items": [
            {"id": r.id, "delta": r.delta, "balance_after": r.balance_after, "kind": r.kind,
             "reason": r.reason, "actor_id": r.actor_id, "created_at": r.created_at.isoformat()}
            for r in rows
        ],
    }


@router.post("/credits/all")
def grant_all(payload: schemas.AdminGrantAllIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Accorder des crédits à TOUS les utilisateurs."""
    try:
        count = credit_service.admin_grant_all(db, admin.id, payload.amount, payload.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"users_granted": count, "amount": payload.amount}


# ---------- Paramètres ----------


@router.get("/settings")
def get_settings_view(db: Session = Depends(get_db)):
    """Réglages applicatifs + état des fournisseurs IA (clés JAMAIS exposées)."""
    return {"settings": credit_service.get_all_settings(db), "providers": ai.available()}


@router.put("/settings")
def put_settings(payload: schemas.AdminSettingsPut, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Modifier les coûts, le renouvellement horaire, les fonctions IA et les limites."""
    updated, errors = {}, {}
    for key, value in payload.settings.items():
        if key not in credit_service.EDITABLE_SETTINGS:
            errors[key] = "Réglage inconnu ou non modifiable."
            continue
        try:
            if key.startswith("cost.") or key.startswith("credits.") or key.startswith("limits."):
                value = int(value)
                if value < 0 or value > 1_000_000:
                    raise ValueError("Valeur hors bornes (0 – 1 000 000).")
            elif key.startswith("features."):
                value = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes", "on")
            credit_service.set_setting(db, key, value, actor_id=admin.id)
            updated[key] = value
        except ValueError as e:
            errors[key] = str(e)
    db.commit()
    if not updated and errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
    return {"updated": updated, "errors": errors}


# ---------- Journaux ----------

@router.get("/logs")
def logs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    """Actions administrateur + erreurs techniques récentes."""
    admin_rows = db.execute(select(AdminLog).order_by(AdminLog.created_at.desc()).limit(limit)).scalars().all()
    error_rows = db.execute(
        select(AuditLog).where(AuditLog.level == "ERROR").order_by(AuditLog.created_at.desc()).limit(limit)
    ).scalars().all()
    return {
        "admin": [
            {"action": r.action, "actor_id": r.actor_id, "target_user_id": r.target_user_id,
             "details": r.details, "created_at": r.created_at.isoformat()}
            for r in admin_rows
        ],
        "errors": [
            {"message": r.message, "context": r.context, "created_at": r.created_at.isoformat()}
            for r in error_rows
        ],
    }


@router.get("/generations")
def admin_generations(
    kind: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Toutes les générations (avec filtres) pour le suivi administratif."""
    q = select(Generation)
    if kind:
        q = q.where(Generation.kind == kind.upper())
    if status_:
        q = q.where(Generation.status == status_.upper())
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(q.order_by(Generation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "total": total,
        "items": [
            {**schemas.GenerationOut.from_gen(g).model_dump(), "user_id": g.user_id}
            for g in rows
        ],
    }
