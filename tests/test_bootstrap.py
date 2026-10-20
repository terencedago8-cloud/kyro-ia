"""Test du bootstrap administrateur (création au démarrage, idempotence, garde-fous)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

tmp = Path(tempfile.mkdtemp()) / "bootstrap_test.db"

# --- Cas 1 : création du premier admin au démarrage du service --------------
os.environ["KYRO_DATABASE_URL"] = f"sqlite:///{tmp}"
os.environ["ADMIN_EMAIL"] = "boss@kyro-ai.com"
os.environ["ADMIN_USERNAME"] = "boss"
os.environ["ADMIN_PASSWORD"] = "KyroAdmin!2026"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

with TestClient(app):
    pass  # lifespan exécuté → schéma + bootstrap

from backend.database import SessionLocal  # noqa: E402
from backend.models import User  # noqa: E402
from backend.security import verify_password  # noqa: E402

db = SessionLocal()
admin = db.query(User).filter(User.email == "boss@kyro-ai.com").first()
assert admin is not None, "L'admin n'a pas été créé au démarrage."
assert admin.role == "ADMIN", f"Rôle incorrect : {admin.role}"
assert verify_password("KyroAdmin!2026", admin.password_hash), "Le mot de passe ne vérifie pas."
n_admins, n_users = db.query(User).filter(User.role == "ADMIN").count(), db.query(User).count()
db.close()
print(f"[OK] Admin créé : {admin.username} <{admin.email}> rôle={admin.role} "
      f"(admins={n_admins}, users={n_users})")
assert n_admins == 1 and n_users == 1, "Duplication à la création !"

# --- Cas 2 : un second démarrage ne doit RIEN créer / RIEN écraser -----------
with TestClient(app):
    pass

db = SessionLocal()
a2, u2 = db.query(User).filter(User.role == "ADMIN").count(), db.query(User).count()
db.close()
assert a2 == 1 and u2 == 1, f"2e démarrage a modifié la base ! admins={a2} users={u2}"
print("[OK] Idempotence : 2e démarrage → aucun doublon, rien d'écrasé.")

# --- Cas 3 : mot de passe trop court → refusé, aucun compte créé -------------
import backend.bootstrap as bs  # noqa: E402
from backend.database import Base  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

engine3 = create_engine(f"sqlite:///{Path(tempfile.mkdtemp())}/weak.db")
Base.metadata.create_all(bind=engine3)
db3 = sessionmaker(bind=engine3)()


class WeakSettings:
    admin_email = "weak@kyro-ai.com"
    admin_username = "weak"
    admin_password = "court12"  # 7 caractères < 8


class NoAdminEnv:
    admin_email = None
    admin_username = "admin"
    admin_password = None


orig = bs.settings
bs.settings = WeakSettings()
created_weak = bs.bootstrap_admin(db3)
n_after_weak = db3.query(User).count()

bs.settings = NoAdminEnv()
created_none = bs.bootstrap_admin(db3)
n_after_none = db3.query(User).count()
bs.settings = orig

assert created_weak is False and n_after_weak == 0, "Mot de passe court accepté !"
assert created_none is False and n_after_none == 0, "Admin créé sans variables !"
assert bs.MIN_PASSWORD_LENGTH == 8
print(f"[OK] Mot de passe < {bs.MIN_PASSWORD_LENGTH} caractères → refusé (0 compte créé).")
print("[OK] Variables absentes → aucune création silencieuse.")

# --- Cas 4 : n'écrase jamais un admin existant -------------------------------
db = SessionLocal()
class ExistingAdmin:
    admin_email = "intrus@evil.com"
    admin_username = "intrus"
    admin_password = "MotDePasse123"

bs.settings = ExistingAdmin()
created_existing = bs.bootstrap_admin(db)
db.close()
assert created_existing is False, "Un 2e admin a été créé alors qu'un existe !"
print("[OK] Un admin existe déjà → bootstrap refusé (aucun écrasement).")

print("\nBOOTSTRAP : 5/5 vérifications réussies.")
