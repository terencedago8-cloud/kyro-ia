"""Initialisation PostgreSQL pour KYRO AI.

À exécuter APRÈS l'installation de PostgreSQL :
    python -m scripts.setup_postgres

Étapes :
 1. Connexion au superuser `postgres` (mot de passe lu dans .pg_super_password.txt)
 2. Création du rôle `kyro` (mot de passe dédié, moindre privilège) + base `kyro`
 3. Création du schéma complet dans la base `kyro`
 4. Création du premier compte ADMIN — identifiants dans les variables ADMIN_EMAIL /
    ADMIN_USERNAME / ADMIN_PASSWORD (surchageables), sinon demandés interactivement.

La base `postgresql+psycopg://...` ciblée est lue depuis KYRO_DATABASE_URL (.env).
"""

import getpass
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.security import hash_password

# IMPORTANT : importer les modèles AVANT tout create_all, sinon Base.metadata est
# vide et "create_all" ne crée aucune table (bug d'ordre d'import).
from backend import credits as credit_service  # noqa: F401
from backend.models import User, UserCredit, utcnow  # noqa: F401

# --- Lecture de la configuration .env (sans pydantic pour rester autonome) ---

def load_env() -> dict:
    env = {}
    p = Path(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def parse_target(url: str) -> tuple[str, str, str, str]:
    """Extrait (hôte, port, base, utilisateur) d'une URL SQLAlchemy."""
    # postgresql+psycopg://user:pass@host:port/dbname
    core = url.split("//", 1)[-1]
    cred, hostpart = core.split("@", 1)
    user = cred.split(":", 1)[0]
    hostport, dbname = hostpart.split("/", 1)
    if ":" in hostport:
        host, port = hostport.split(":", 1)
    else:
        host, port = hostport, "5432"
    return host, port, dbname, user


def main() -> None:
    env = load_env()
    target_url = os.environ.get("KYRO_DATABASE_URL") or env.get(
        "KYRO_DATABASE_URL", "postgresql+psycopg://kyro:kyro@localhost:5432/kyro"
    )

    if not target_url.startswith("postgresql"):
        print(f"KYRO_DATABASE_URL n'est pas une URL PostgreSQL ({target_url.split(':')[0]}).")
        print("Renseignez-la dans .env (voir .env.example) puis relancez.")
        sys.exit(1)

    host, port, dbname, dbuser = parse_target(target_url)

    # Mot de passe du superuser d'installation
    super_pw_file = Path(".pg_super_password.txt")
    if super_pw_file.exists():
        super_pw = super_pw_file.read_text(encoding="ascii").strip()
    else:
        super_pw = getpass.getpass("Mot de passe du superuser postgres : ")

    # Mot de passe du rôle applicatif (dans l'URL cible, sinon demandé)
    try:
        app_pw = target_url.split("//", 1)[1].split("@", 1)[0].split(":", 1)[1]
    except IndexError:
        app_pw = getpass.getpass(f"Mot de passe pour le rôle {dbuser} : ")

    print(f"1/4 Connexion au serveur {host}:{port} en tant que postgres…")
    admin_url = f"postgresql+psycopg://postgres:{super_pw}@{host}:{port}/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    print(f"2/4 Création du rôle '{dbuser}' et de la base '{dbname}' (si absents)…")
    # PostgreSQL refuse le paramétrage ($1) dans CREATE/ALTER ROLE, et psycopg.sql
    # exige un contexte de rendu → on quote nous-mêmes (règles PostgreSQL) :
    #   identifiant → "..." avec " doublé ; littéral → '...' avec ' doublée.
    def qi(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def ql(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": dbuser}
        ).scalar()
        if not exists:
            conn.exec_driver_sql(f"CREATE ROLE {qi(dbuser)} LOGIN PASSWORD {ql(app_pw)}")
            print(f"      rôle '{dbuser}' créé.")
        else:
            print(f"      rôle '{dbuser}' existe déjà.")
        conn.exec_driver_sql(f"ALTER ROLE {qi(dbuser)} LOGIN PASSWORD {ql(app_pw)}")

        has_db = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": dbname}
        ).scalar()
        if not has_db:
            conn.exec_driver_sql(f"CREATE DATABASE {qi(dbname)} OWNER {qi(dbuser)}")
            print(f"      base '{dbname}' créée.")
        else:
            print(f"      base '{dbname}' existe déjà.")
    admin_engine.dispose()

    print("3/4 Création du schéma (tables)…")
    db_engine = create_engine(target_url)
    Base.metadata.create_all(bind=db_engine)
    print("      tables créées/vérifiées.")

    print("4/4 Premier administrateur…")
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        # Identifiants : variables d'environnement > .env > défauts demandés
        email = (
            os.environ.get("ADMIN_EMAIL")
            or env.get("ADMIN_EMAIL")
            or input("E-mail de l'administrateur [admin@kyro-ai.com]: ").strip()
            or "admin@kyro-ai.com"
        )
        username = (
            os.environ.get("ADMIN_USERNAME")
            or env.get("ADMIN_USERNAME")
            or input("Pseudo [admin]: ").strip()
            or "admin"
        )
        password = os.environ.get("ADMIN_PASSWORD") or env.get("ADMIN_PASSWORD")

        if db.query(User).filter(User.email == email.lower()).first():
            print(f"      L'admin {email} existe déjà — rien à faire.")
        else:
            if not password:
                password = getpass.getpass("Mot de passe de l'administrateur : ")
                if password != getpass.getpass("Confirmez : "):
                    print("      Les mots de passe ne correspondent pas.", file=sys.stderr)
                    sys.exit(1)
            if len(password) < 8:
                print("      Mot de passe trop court (min. 8 caractères).", file=sys.stderr)
                sys.exit(1)
            u = User(
                email=email.lower(),
                username=username,
                password_hash=hash_password(password),
                role="ADMIN",
            )
            db.add(u)
            db.flush()
            initial = credit_service.get_int_setting(db, credit_service.HOURLY_GRANT_KEY)
            db.add(UserCredit(user_id=u.id, balance=initial, period_start=utcnow()))
            db.commit()
            print(f"      Administrateur créé : {username} <{email}> — {initial} crédits.")
    finally:
        db.close()
        db_engine.dispose()

    print("\nPostgreSQL initialisé. Lancez le serveur :")
    print("  uvicorn backend.main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
