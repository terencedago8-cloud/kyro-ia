"""Vérification rapide de la base PostgreSQL KYRO AI (lecture seule).

    python -m scripts.verify_postgres
"""

from sqlalchemy import text

from backend.database import DB_URL, engine


def mask(url: str) -> str:
    """Masque le mot de passe de l'URL pour l'affichage."""
    if "@" not in url or "//" not in url:
        return url
    head, tail = url.split("@", 1)
    user = head.split("//", 1)[1].split(":", 1)[0]
    return f"postgresql+psycopg://{user}:****@{tail}"


def main() -> None:
    print(f"Base   : {mask(DB_URL)}")
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        ).scalars().all()
        print(f"Tables ({len(tables)}) : {', '.join(tables)}")

        users = conn.execute(text("SELECT email, username, role FROM users ORDER BY id")).all()
        for email, username, role in users:
            print(f"  - {username} <{email}> rôle={role}")

        balances = conn.execute(
            text("SELECT u.email, c.balance FROM user_credits c JOIN users u ON u.id = c.user_id")
        ).all()
        print(f"Soldes : {balances}")

        ledger = conn.execute(text("SELECT count(*) FROM credit_ledger")).scalar()
        audit = conn.execute(text("SELECT count(*) FROM audit_logs")).scalar()
        print(f"Ledger : {ledger} écriture(s)")
        print(f"Audit  : {audit} entrée(s)")

    print("\nPostgreSQL opérationnel.")


if __name__ == "__main__":
    main()
