"""Inscription / connexion (avec protection anti-force-brute)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import credits as credit_service
from .. import schemas
from ..database import get_db
from ..deps import get_client_ip
from ..models import LoginAttempt, User, UserCredit, utcnow
from ..security import (
    create_access_token,
    hash_password,
    is_login_blocked,
    login_window_start,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    """Crée un compte. Le premier solde = un renouvellement horaire (200 crédits par défaut)."""
    user = User(
        email=payload.email.lower().strip(),
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role="USER",  # le rôle ADMIN ne peut PAS être choisi à l'inscription
    )
    db.add(user)
    db.flush()
    initial = credit_service.get_int_setting(db, credit_service.HOURLY_GRANT_KEY)
    db.add(UserCredit(user_id=user.id, balance=initial, period_start=utcnow()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet e-mail ou ce pseudo est déjà utilisé.")

    token = create_access_token(user.id, user.role)
    return schemas.TokenOut(access_token=token, user=schemas.UserOut.from_user(user))


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    """Connexion. 5 échecs consécutifs en 15 min = blocage temporaire."""
    ip = get_client_ip(request)
    window_start = login_window_start()
    attempts = db.execute(
        select(LoginAttempt).where(LoginAttempt.email == payload.email.lower(), LoginAttempt.created_at >= window_start)
    ).scalars().all()

    if is_login_blocked(attempts):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de tentatives de connexion échouées. Réessayez dans quelques minutes.",
        )

    user = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    ok = user is not None and verify_password(payload.password, user.password_hash)

    db.add(LoginAttempt(email=payload.email.lower(), ip=ip, success=ok))

    if not ok:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect.")
    if user.is_suspended:
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce compte est suspendu. Contactez l'administrateur.")

    user.last_login = utcnow()
    db.commit()

    token = create_access_token(user.id, user.role)
    return schemas.TokenOut(access_token=token, user=schemas.UserOut.from_user(user))
