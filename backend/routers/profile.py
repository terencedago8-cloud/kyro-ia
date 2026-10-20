"""Profil : solde de crédits, compte à rebours du renouvellement, historique, modification du compte."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import credits as credit_service
from .. import schemas
from ..database import get_db
from ..deps import get_current_user
from ..models import CreditLedger, Generation, User
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/me", tags=["profile"])


@router.get("")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Profil + portefeuille : solde, montant du prochain versement, temps restant."""
    snapshot = credit_service.get_balance_snapshot(db, user.id)
    generations = db.execute(
        select(func.count()).select_from(Generation).where(Generation.user_id == user.id)
    ).scalar() or 0
    successes = db.execute(
        select(func.count()).select_from(Generation).where(Generation.user_id == user.id, Generation.status == "SUCCESS")
    ).scalar() or 0
    return {
        "user": schemas.UserOut.from_user(user),
        "credits": snapshot,
        "stats": {"generations": generations, "successes": successes},
    }


@router.patch("")
def update_profile(payload: schemas.ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Modifier le pseudo et/ou le mot de passe (mot de passe actuel requis)."""
    if payload.username:
        user.username = payload.username.strip()
    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect.")
        user.password_hash = hash_password(payload.new_password)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce pseudo est déjà utilisé.")
    return {"user": schemas.UserOut.from_user(user)}


@router.get("/credits/history")
def credits_history(
    page: int = 1,
    page_size: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Journal des mouvements de crédits de l'utilisateur."""
    q = select(CreditLedger).where(CreditLedger.user_id == user.id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(
        q.order_by(CreditLedger.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id, "delta": r.delta, "balance_after": r.balance_after, "kind": r.kind,
                "reason": r.reason, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
