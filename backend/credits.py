"""Moteur de crédits KYRO AI.

Garanties :
- Déduction UNIQUEMENT côté serveur, dans une transaction avec verrouillage (FOR UPDATE)
  → impossible d'avoir un solde incorrect ou de doubler une déduction.
- Idempotence : chaque demande porte un `request_id` unique ; une seconde tentative
  de déduction pour la même demande est ignorée.
- Renouvellement horaire automatique, non cumulatif (solde remis à `credits.hourly_grant`),
  appliqué même si l'utilisateur était déconnecté (dérivé de `period_start`).
- Remboursement automatique en cas d'échec de génération.
- Chaque mouvement est écrit dans le journal d'audit `credit_ledger`.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AdminLog, CreditLedger, Setting, UserCredit, utcnow

# ---------- Clés de réglages ----------

HOURLY_GRANT_KEY = "credits.hourly_grant"

COST_KEYS = {
    "CHAT": "cost.chat",
    "IMAGE": "cost.image",
    "VIDEO": "cost.video",
    "CODE": "cost.code",
}

FEATURE_KEYS = {
    "CHAT": "features.chat",
    "IMAGE": "features.image",
    "VIDEO": "features.video",
    "CODE": "features.code",
}

LIMIT_KEYS = {
    "max_prompt_length": "limits.max_prompt_length",
    "max_concurrent_generations": "limits.max_concurrent_generations",
    "max_generations_per_hour": "limits.max_generations_per_hour",
}

#: Valeurs par défaut (utilisées tant qu'aucune valeur n'est enregistrée en base)
DEFAULT_SETTINGS: dict[str, object] = {
    HOURLY_GRANT_KEY: 200,
    "cost.chat": 3,
    "cost.image": 3,
    "cost.video": 3,
    "cost.code": 3,
    "features.chat": True,
    "features.image": True,
    "features.video": True,
    "features.code": True,
    "limits.max_prompt_length": 4000,
    "limits.max_concurrent_generations": 2,
    "limits.max_generations_per_hour": 60,
}

#: Whitelist des réglages modifiables par l'administrateur
EDITABLE_SETTINGS = set(DEFAULT_SETTINGS)


# ---------- Réglages ----------

def get_setting(db: Session, key: str):
    row = db.get(Setting, key)
    if row is not None:
        try:
            import json

            return json.loads(row.value)
        except ValueError:
            return DEFAULT_SETTINGS.get(key)
    return DEFAULT_SETTINGS.get(key)


def get_int_setting(db: Session, key: str) -> int:
    try:
        return int(get_setting(db, key))
    except (TypeError, ValueError):
        return int(DEFAULT_SETTINGS.get(key, 0))


def get_bool_setting(db: Session, key: str) -> bool:
    return bool(get_setting(db, key))


def set_setting(db: Session, key: str, value, actor_id: str | None = None) -> None:
    import json

    if key not in EDITABLE_SETTINGS:
        raise ValueError(f"Réglage non modifiable : {key}")
    row = db.get(Setting, key)
    encoded = json.dumps(value)
    if row is None:
        db.add(Setting(key=key, value=encoded))
    else:
        row.value = encoded
    if actor_id:
        db.add(AdminLog(actor_id=actor_id, action="SETTING_UPDATED", details={"key": key, "value": value}))


def get_all_settings(db: Session) -> dict:
    return {key: get_setting(db, key) for key in sorted(EDITABLE_SETTINGS)}


# ---------- Renouvellement horaire ----------

def _aware(dt: datetime) -> datetime:
    """SQLite stocke des datetimes sans fuseau : on assume UTC pour comparer correctement."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def apply_renewal_locked(db: Session, credit: UserCredit, now: datetime | None = None) -> bool:
    """Applique le renouvellement horaire si une heure est écoulée.

    NON CUMULATIF : le solde est remis à `credits.hourly_grant` (jamais multiplié
    par le nombre d'heures passées). `period_start` avance d'autant d'heures entières.
    Doit être appelé avec la ligne `user_credits` verrouillée (FOR UPDATE).
    Retourne True si un renouvellement a eu lieu.
    """
    now = _aware(now or utcnow())
    credit.period_start = _aware(credit.period_start)
    elapsed = (now - credit.period_start).total_seconds()
    if elapsed < 3600:
        return False

    hours = int(elapsed // 3600)
    grant = get_int_setting(db, HOURLY_GRANT_KEY)
    old_balance = credit.balance
    credit.balance = grant
    credit.period_start = credit.period_start + timedelta(hours=hours)
    db.add(
        CreditLedger(
            user_id=credit.user_id,
            delta=grant - old_balance,
            balance_after=grant,
            kind="RENEWAL",
            reason=f"Renouvellement horaire automatique (+{grant} crédits)",
        )
    )
    return True


def lock_credit(db: Session, user_id: str) -> UserCredit:
    """Verrouille la ligne de crédits pour toute la transaction (évite les courses)."""
    return (
        db.execute(select(UserCredit).where(UserCredit.user_id == user_id).with_for_update())
        .scalar_one()
    )


def renew_all(db: Session) -> int:
    """Renouvellement pour TOUS les utilisateurs (boucle d'arrière-plan, toutes les minutes).

    Ainsi les soldes sont actualisés même pour les comptes déconnectés.
    Retourne le nombre de comptes renouvelés.
    """
    now = utcnow()
    rows = db.execute(select(UserCredit).with_for_update()).scalars().all()
    count = 0
    for credit in rows:
        if apply_renewal_locked(db, credit, now):
            count += 1
    if count:
        db.commit()
    return count


# ---------- Consommation / remboursement ----------

class CreditError(Exception):
    """Erreur métier liée aux crédits."""


class InsufficientCredits(CreditError):
    def __init__(self, balance: int, cost: int):
        self.balance = balance
        self.cost = cost
        super().__init__(
            f"Crédits insuffisants : cette demande coûte {cost} crédits "
            f"et votre solde est de {balance}. Attendez le prochain renouvellement horaire."
        )


def consume_credits(db: Session, user_id: str, amount: int, kind: str, request_id: str, reason: str = "") -> CreditLedger:
    """Débite `amount` crédits UNE SEULE FOIS pour la demande `request_id`.

    - Verrouillage de la ligne + renouvellement appliqué avant vérification.
    - Si `request_id` a déjà été débité, retourne l'écriture existante (idempotence).
    - Sinon lève InsufficientCredits (aucun débit, transaction annulée).
    """
    # Idempotence : une seule déduction par demande acceptée.
    existing = db.execute(
        select(CreditLedger).where(CreditLedger.request_id == request_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    credit = lock_credit(db, user_id)
    apply_renewal_locked(db, credit)

    if credit.balance < amount:
        db.rollback()  # libère le verrou, aucun débit
        raise InsufficientCredits(credit.balance, amount)

    credit.balance -= amount
    entry = CreditLedger(
        user_id=user_id,
        delta=-amount,
        balance_after=credit.balance,
        kind="CONSUME",
        reason=reason or f"Déduction : {kind}",
        request_id=request_id,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        # Course critique : une déduction simultanée pour le même request_id a gagné.
        db.rollback()
        return db.execute(
            select(CreditLedger).where(CreditLedger.request_id == request_id)
        ).scalar_one()
    return entry


def refund_credits(db: Session, user_id: str, amount: int, request_id: str, reason: str = "Remboursement automatique — génération échouée") -> bool:
    """Rembourse une génération échouée (une seule fois grâce à l'unicité du request_id)."""
    if amount <= 0:
        return False
    credit = lock_credit(db, user_id)
    apply_renewal_locked(db, credit)
    credit.balance += amount
    db.add(
        CreditLedger(
            user_id=user_id,
            delta=amount,
            balance_after=credit.balance,
            kind="REFUND",
            reason=reason,
            request_id=f"refund:{request_id}",
        )
    )
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()  # déjà remboursé
        return False


# ---------- Opérations administrateur ----------

ADMIN_KINDS = {
    "add": "ADMIN_ADD",
    "remove": "ADMIN_REMOVE",
    "set": "ADMIN_SET",
    "reset": "ADMIN_RESET",
}


def admin_adjust_credits(
    db: Session,
    actor_id: str,
    user_id: str,
    action: str,
    amount: int | None,
    reason: str,
) -> UserCredit:
    """Ajouter / retirer / définir / réinitialiser le solde d'un utilisateur, avec raison obligatoire."""
    if action not in ADMIN_KINDS:
        raise ValueError("Action invalide (add | remove | set | reset).")
    if not reason or not reason.strip():
        raise ValueError("Une raison est obligatoire pour toute opération de crédits.")
    if action in ("add", "remove", "set") and (amount is None or amount < 0):
        raise ValueError("Un montant positif est requis.")

    credit = lock_credit(db, user_id)
    apply_renewal_locked(db, credit)
    old = credit.balance

    if action == "add":
        credit.balance = old + int(amount)
    elif action == "remove":
        credit.balance = max(0, old - int(amount))
    elif action == "set":
        credit.balance = int(amount)
    elif action == "reset":
        credit.balance = get_int_setting(db, HOURLY_GRANT_KEY)
        credit.period_start = utcnow()

    db.add(
        CreditLedger(
            user_id=user_id,
            actor_id=actor_id,
            delta=credit.balance - old,
            balance_after=credit.balance,
            kind=ADMIN_KINDS[action],
            reason=reason.strip(),
        )
    )
    db.add(
        AdminLog(
            actor_id=actor_id,
            action=f"CREDITS_{ADMIN_KINDS[action]}",
            target_user_id=user_id,
            details={"amount": amount, "reason": reason.strip(), "old_balance": old, "new_balance": credit.balance},
        )
    )
    db.commit()
    db.refresh(credit)
    return credit


def admin_grant_all(db: Session, actor_id: str, amount: int, reason: str) -> int:
    """Accorde des crédits à TOUS les utilisateurs (journalisé par compte)."""
    if amount <= 0:
        raise ValueError("Le montant doit être positif.")
    if not reason or not reason.strip():
        raise ValueError("Une raison est obligatoire.")
    now = utcnow()
    rows = db.execute(select(UserCredit).with_for_update()).scalars().all()
    for credit in rows:
        old = credit.balance
        credit.balance = old + amount
        db.add(
            CreditLedger(
                user_id=credit.user_id,
                actor_id=actor_id,
                delta=amount,
                balance_after=credit.balance,
                kind="ADMIN_GRANT_ALL",
                reason=reason.strip(),
            )
        )
    db.add(AdminLog(actor_id=actor_id, action="CREDITS_GRANT_ALL", details={"amount": amount, "users": len(rows), "reason": reason.strip()}))
    db.commit()
    return len(rows)


# ---------- Lecture du solde (côté API) ----------

def get_balance_snapshot(db: Session, user_id: str) -> dict:
    """Solde + délai restant avant le prochain renouvellement (applique le renouvellement si dû)."""
    credit = lock_credit(db, user_id)
    if apply_renewal_locked(db, credit):
        db.commit()
    grant = get_int_setting(db, HOURLY_GRANT_KEY)
    now = utcnow()
    next_renewal = _aware(credit.period_start) + timedelta(hours=1)
    seconds_left = max(0, int((next_renewal - now).total_seconds()))
    return {
        "balance": credit.balance,
        "hourly_grant": grant,
        "period_start": credit.period_start.isoformat(),
        "seconds_until_renewal": seconds_left,
        "next_renewal_at": next_renewal.isoformat(),
    }


def count_consumed(db: Session, since: datetime | None = None) -> int:
    q = select(func.coalesce(func.sum(func.abs(CreditLedger.delta)), 0)).where(CreditLedger.kind == "CONSUME")
    if since:
        q = q.where(CreditLedger.created_at >= since)
    return int(db.execute(q).scalar() or 0)
