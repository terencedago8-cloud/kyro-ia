"""Test du moteur de crédits : idempotence, concurrence, remboursement (PostgreSQL requis pour FOR UPDATE).

La base étant persistante, chaque exécution utilise des comptes ET des `request_id`
uniques : la colonne `credit_ledger.request_id` est UNIQUE (c'est ce qui garantit
l'idempotence des déductions en production).
"""
import sys
import threading
import time
from datetime import timedelta

sys.path.insert(0, ".")

from backend import credits as credit_service
from backend.database import Base, SessionLocal, engine
from backend.models import User, UserCredit, utcnow
from backend.security import hash_password

Base.metadata.create_all(bind=engine)
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        print(f"  [ÉCHEC] {name} {extra}")


RUN_TAG = int(time.time())  # comptes de test uniques à chaque exécution


def rid(tag: str) -> str:
    """request_id unique par exécution (contrainte UNIQUE en base)."""
    return f"{tag}-{RUN_TAG}"


def fresh_user(tag, balance=100):
    db = SessionLocal()
    u = User(
        email=f"{tag}{RUN_TAG}@engine.test",
        username=f"eng_{tag}{RUN_TAG % 100000}",
        password_hash=hash_password("x" * 10),
        role="USER",
    )
    db.add(u)
    db.flush()
    db.add(UserCredit(user_id=u.id, balance=balance, period_start=utcnow()))
    db.commit()
    uid = u.id
    db.close()
    return uid


def balance_of(uid):
    db = SessionLocal()
    b = db.get(UserCredit, uid).balance
    db.close()
    return b


print("== 1. Idempotence : une seule déduction par request_id ==")
uid = fresh_user("idem")
db = SessionLocal()
rid_unique = rid("req-unique")
credit_service.consume_credits(db, uid, 3, "CHAT", rid_unique, "test")
credit_service.consume_credits(db, uid, 3, "CHAT", rid_unique, "test")  # tentative de double
credit_service.consume_credits(db, uid, 3, "CHAT", rid_unique, "test")  # encore
db.close()
check("3 appels avec le même request_id → 1 seule déduction (100→97)", balance_of(uid) == 97, f"({balance_of(uid)})")

print("== 2. Solde insuffisant → exception + aucun débit ==")
uid = fresh_user("insuf", balance=2)
db = SessionLocal()
try:
    credit_service.consume_credits(db, uid, 3, "IMAGE", rid("req-insuf"), "test")
    check("InsufficientCredits levée", False)
except credit_service.InsufficientCredits:
    check("InsufficientCredits levée", True)
db.close()
check("Aucun débit si refus (solde inchangé)", balance_of(uid) == 2)

print("== 3. Remboursement idempotent ==")
uid = fresh_user("refund")
db = SessionLocal()
rid_refund = rid("req-refund")
credit_service.consume_credits(db, uid, 3, "VIDEO", rid_refund, "test")
credit_service.refund_credits(db, uid, 3, rid_refund)  # 1er remboursement
credit_service.refund_credits(db, uid, 3, rid_refund)  # double remboursement bloqué
db.close()
check("Consume + 2 refunds → solde d'origine (pas de double)", balance_of(uid) == 100, f"({balance_of(uid)})")

print("== 4. Renouvellement non cumulatif (multiple heures) ==")
uid = fresh_user("renew", balance=15)
db = SessionLocal()
c = db.get(UserCredit, uid)
c.period_start = utcnow() - timedelta(hours=5)  # 5 h de déconnexion
db.commit()
credit_service.renew_all(db)
db.close()
check("5 h de déconnexion → solde = 200 (et non 5×200)", balance_of(uid) == 200, f"({balance_of(uid)})")

print("== 5. Concurrence : 10 déductions simultanées, même request_id ==")
uid = fresh_user("conc", balance=1000)
rid_conc = rid("req-conc")
errors = []


def worker():
    try:
        db = SessionLocal()
        credit_service.consume_credits(db, uid, 3, "CHAT", rid_conc, "conc")
        db.close()
    except Exception as e:  # noqa: BLE001
        errors.append(e)


threads = [threading.Thread(target=worker) for _ in range(10)]
[t.start() for t in threads]
[t.join() for t in threads]
check("10 threads × même request_id → 1 seule déduction (1000→997)", balance_of(uid) == 997 and not errors, f"({balance_of(uid)}, err={errors[:1]})")

print("== 6. Concurrence : 10 déductions distinctes (courses sur le solde) ==")
uid = fresh_user("conc2", balance=10)
errors = []


def worker2(i):
    try:
        db = SessionLocal()
        credit_service.consume_credits(db, uid, 3, "IMAGE", f"req-distinct-{RUN_TAG}-{i}", "conc")
        db.close()
    except credit_service.InsufficientCredits:
        pass
    except Exception as e:  # noqa: BLE001
        errors.append(e)


threads = [threading.Thread(target=worker2, args=(i,)) for i in range(10)]
[t.start() for t in threads]
[t.join() for t in threads]
b = balance_of(uid)
check("10 demandes distinctes, solde 10 → exactement 3 acceptées (solde 1)", b == 1 and not errors, f"({b}, err={errors[:1]})")

print(f"\n{'='*40}\nRÉSULTAT MOTEUR : {ok} réussis, {fail} échec(s)")
sys.exit(1 if fail else 0)
