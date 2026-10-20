"""Sécurité : hachage des mots de passe (PBKDF2), jetons JWT, anti-force-brute."""

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    """Hachage irréversible — un mot de passe n'est JAMAIS stocké en clair."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Décodage strict : signature ET date d'expiration vérifiées."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# ---------- Protection anti-force-brute ----------

LOGIN_WINDOW_SECONDS = settings.login_block_minutes * 60


def is_login_blocked(attempts: list) -> bool:
    """True si trop d'échecs récents (fenêtre glissante)."""
    recent_failures = [a for a in attempts if not a.success]
    return len(recent_failures) >= settings.login_max_attempts


def login_window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=LOGIN_WINDOW_SECONDS)
