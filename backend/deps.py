"""Dépendances FastAPI : utilisateur courant, rôle administrateur, limites d'usage."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import credits as credit_service
from .database import get_db
from .models import Generation, User, utcnow
from .security import decode_access_token
from datetime import datetime, timedelta


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Récupère l'utilisateur depuis le jeton Bearer. Le rôle est relu en base à chaque requête."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")
    payload = decode_access_token(auth[len("Bearer "):])
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré. Reconnectez-vous.")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable.")
    if user.is_suspended:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce compte est suspendu. Contactez l'administrateur.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Toute route administrateur exige le rôle ADMIN en base — jamais depuis le client."""
    if user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé aux administrateurs.")
    return user


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


class CreditsRequired:
    """Vérifie solde suffisant + fonction activée + limites avant même de consommer."""

    def __init__(self, kind: str):
        self.kind = kind

    def __call__(self, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
        cost_key = credit_service.COST_KEYS.get(self.kind)
        feature_key = credit_service.FEATURE_KEYS.get(self.kind)

        if feature_key and not credit_service.get_bool_setting(db, feature_key):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"La fonction « {self.kind} » est temporairement désactivée par l'administrateur.")

        # Limite de générations simultanées
        max_concurrent = credit_service.get_int_setting(db, credit_service.LIMIT_KEYS["max_concurrent_generations"])
        active = db.execute(
            select(func.count()).select_from(Generation).where(
                Generation.user_id == user.id,
                Generation.kind.in_(["IMAGE", "VIDEO"]),
                Generation.status.in_(["PENDING", "RUNNING"]),
            )
        ).scalar() or 0
        if self.kind in ("IMAGE", "VIDEO") and active >= max_concurrent:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Vous avez déjà {active} génération(s) en cours (maximum {max_concurrent}). Attendrez qu'elles se terminent.",
            )

        # Quota horaire
        max_per_hour = credit_service.get_int_setting(db, credit_service.LIMIT_KEYS["max_generations_per_hour"])
        window_start = datetime.now(utcnow().tzinfo) - timedelta(hours=1)
        recent = db.execute(
            select(func.count()).select_from(Generation).where(
                Generation.user_id == user.id, Generation.created_at >= window_start
            )
        ).scalar() or 0
        if recent >= max_per_hour:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Limite horaire atteinte ({max_per_hour} demandes/heure). Réessayez plus tard.")

        # Solde suffisant ? (renouvellement appliqué à la volée)
        cost = credit_service.get_int_setting(db, cost_key) if cost_key else 0
        snapshot = credit_service.get_balance_snapshot(db, user.id)
        if snapshot["balance"] < cost:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Crédits insuffisants : cette demande coûte {cost} crédits, "
                f"votre solde est de {snapshot['balance']}. "
                f"Prochain renouvellement dans {snapshot['seconds_until_renewal']} s (+{snapshot['hourly_grant']} crédits).",
            )
        request.state.credit_cost = cost
        return user


def check_prompt_length(db: Session, prompt: str) -> None:
    """Limite de longueur du prompt (réglable par l'administrateur)."""
    max_len = credit_service.get_int_setting(db, credit_service.LIMIT_KEYS["max_prompt_length"])
    if not prompt or not prompt.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le prompt ne peut pas être vide.")
    if len(prompt) > max_len:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Le prompt est trop long ({len(prompt)} caractères, maximum {max_len}).",
        )
