"""Création sécurisée du premier administrateur au démarrage du serveur.

Nécessaire là où aucun accès shell n'existe (Render, PaaS…). Règles :
- Ne s'exécute QUE si aucun compte ADMIN n'existe (uniquement le tout premier).
- Piloté par des variables d'environnement CÔTÉ SERVEUR (ADMIN_EMAIL / ADMIN_PASSWORD),
  jamais par une requête HTTP : aucun utilisateur ne peut secréter un admin via le navigateur.
- Refuse un mot de passe trop court et ne modifie jamais un compte existant.
- Alternative shell : python -m scripts.init_admin
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import User, UserCredit, utcnow
from .security import hash_password

logger = logging.getLogger("kyro.bootstrap")

MIN_PASSWORD_LENGTH = 8


def bootstrap_admin(db: Session) -> bool:
    """Crée le premier ADMIN si nécessaire. Retourne True si un compte a été créé."""
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""

    if not email or not password:
        logger.info("ADMIN_EMAIL/ADMIN_PASSWORD non définis — création d'admin automatique ignorée.")
        return False

    # Un administrateur existe déjà → on n'écrase jamais rien.
    if db.execute(select(User).where(User.role == "ADMIN")).first() is not None:
        logger.info("Au moins un administrateur existe déjà — aucun bootstrap.")
        return False

    if len(password) < MIN_PASSWORD_LENGTH:
        logger.error(
            "ADMIN_PASSWORD trop court (%d caractères, minimum %d) — administrateur NON créé.",
            len(password), MIN_PASSWORD_LENGTH,
        )
        return False

    username = (settings.admin_username or "admin").strip()
    if db.execute(select(User).where(User.email == email)).first() is not None:
        logger.error("Le compte %s existe déjà sans rôle ADMIN — bootstrap refusé.", email)
        return False

    initial = 200
    try:
        from . import credits as credit_service

        initial = credit_service.get_int_setting(db, credit_service.HOURLY_GRANT_KEY)
    except Exception:  # noqa: BLE001 — table settings absente au tout premier amorçage
        logger.warning("Lecture des réglages impossible, solde initial par défaut = %d.", initial)

    user = User(email=email, username=username, password_hash=hash_password(password), role="ADMIN")
    db.add(user)
    db.flush()
    db.add(UserCredit(user_id=user.id, balance=initial, period_start=utcnow()))
    db.commit()
    logger.info("Premier administrateur créé : %s <%s> (%d crédits).", username, email, initial)
    return True
