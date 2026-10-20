"""Connexion à la base de données (PostgreSQL via SQLAlchemy)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def normalize_db_url(url: str) -> str:
    """Normalise l'URL vers le driver psycopg3.

    Render / Railway / Heroku injectent `postgres://` ou `postgresql://`, que psycopg3
    refuse — on convertit en `postgresql+psycopg://` en conservant chemins et paramètres
    (?sslmode=require par ex.).
    """
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DB_URL = normalize_db_url(settings.database_url)

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    future=True,
    # Nécessaire pour SQLite en développement local (sans impact sur PostgreSQL)
    **({"connect_args": {"check_same_thread": False}} if DB_URL.startswith("sqlite") else {}),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dépendance FastAPI : une session par requête, fermée proprement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
