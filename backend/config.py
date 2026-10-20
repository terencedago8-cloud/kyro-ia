"""Configuration Kyro AI — toutes les clés secrètes viennent du fichier .env (variables d'environnement)."""
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KYRO AI"

    # --- Infrastructure ---
    environment: str = "development"
    # Accepte KYRO_DATABASE_URL (.env maison) OU DATABASE_URL (injecté automatiquement par Render,
    # Railway, Heroku…). Le schéma postgres:// est normalisé côté database.py.
    database_url: str = Field(
        default="postgresql+psycopg://kyro:kyro@localhost:5432/kyro",
        validation_alias=AliasChoices("KYRO_DATABASE_URL", "DATABASE_URL"),
    )
    media_dir: str = "media"
    cors_origins: str = "*"

    # --- Premier administrateur (créé AU DÉMARRAGE si aucun admin n'existe) ---
    # Utilisé sur Render/où aucun accès shell n'est disponible. Ignore si absent.
    admin_email: str | None = Field(default=None, validation_alias=AliasChoices("KYRO_ADMIN_EMAIL", "ADMIN_EMAIL"))
    admin_username: str = Field(default="admin", validation_alias=AliasChoices("KYRO_ADMIN_USERNAME", "ADMIN_USERNAME"))
    admin_password: str | None = Field(default=None, validation_alias=AliasChoices("KYRO_ADMIN_PASSWORD", "ADMIN_PASSWORD"))

    # --- Authentification ---
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    login_max_attempts: int = 5
    login_block_minutes: int = 15

    # --- Valeurs par défaut du système de crédits (surchargées par la table `settings`) ---
    default_hourly_grant: int = 200
    default_cost: int = 3

    # --- Fournisseur CHAT (compatible OpenAI) ---
    chat_api_base: str | None = None
    chat_api_key: str | None = None
    chat_model: str = "gpt-4o-mini"

    # --- Fournisseur IMAGES (API Images OpenAI) ---
    image_api_base: str | None = None
    image_api_key: str | None = None
    image_model: str = "gpt-image-1"

    # --- Fournisseur VIDEOS (Replicate) ---
    video_api_base: str = "https://api.replicate.com/v1"
    video_api_key: str | None = None
    video_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KYRO_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
