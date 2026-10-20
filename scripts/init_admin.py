"""Création sécurisée du PREMIER administrateur — exécuté côté serveur uniquement.

Usage :
    python -m scripts.init_admin

Le mot de passe est demandé de façon interactive (jamais dans l'historique du shell).
Un admin ne peut PAS se créer via l'API ni via le navigateur.
"""

import getpass
import sys

from backend import credits as credit_service
from backend.database import Base, SessionLocal, engine
from backend.models import User, UserCredit, utcnow
from backend.security import hash_password


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.role == "ADMIN").count()
        if admins:
            print(f"Un administrateur existe déjà ({admins} au total). Rien à faire.")
            return

        email = input("E-mail de l'administrateur : ").strip().lower()
        username = input("Pseudo : ").strip()
        password = getpass.getpass("Mot de passe (min. 8 caractères) : ")
        if len(password) < 8:
            print("Mot de passe trop court (min. 8 caractères).", file=sys.stderr)
            sys.exit(1)
        confirm = getpass.getpass("Confirmez le mot de passe : ")
        if password != confirm:
            print("Les mots de passe ne correspondent pas.", file=sys.stderr)
            sys.exit(1)

        user = User(email=email, username=username, password_hash=hash_password(password), role="ADMIN")
        db.add(user)
        db.flush()
        initial = credit_service.get_int_setting(db, credit_service.HOURLY_GRANT_KEY)
        db.add(UserCredit(user_id=user.id, balance=initial, period_start=utcnow()))
        db.commit()
        print(f"Administrateur créé : {username} <{email}> (solde initial : {initial} crédits).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
