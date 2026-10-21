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

    # --- Fournisseur VIDEOS (Replicate `r8_…` ou Pollinations `sk_…`) ---
    video_api_base: str = "https://api.replicate.com/v1"
    video_api_key: str | None = None
    video_model: str | None = None

    # --- Repli GRATUIT sans clé : Pollinations (texte + images) ---
    # Activé par défaut : le site génère réellement sans aucune clé API.
    # Le service gratuit limite le débit (~1 texte/30 s et ~1 image/45 s par IP) :
    # en cas de dépassement l'API renvoie un message explicatif + remboursement.
    # Désactiver avec KYRO_FREE_AI=false → 503 tant qu'aucune clé n'est fournie.
    free_ai: bool = True
    free_chat_endpoint: str = "https://text.pollinations.ai/openai"
    free_chat_model: str = "openai-fast"
    free_image_endpoint: str = "https://image.pollinations.ai/prompt"

    # --- Pollinations avec clé : UNE SEULE clé pour chat + images + vidéos ---
    # Clé gratuite obtenue sur https://enter.pollinations.ai/keys (pollen par quêtes),
    # à poser dans KYRO_POLLINATIONS_KEY. Leve les limites de débit et debloque la vidéo.
    pollinations_key: str | None = None
    pollinations_api_base: str = "https://gen.pollinations.ai"
    pollinations_chat_model: str = "openai/gpt-4o-mini"
    pollinations_image_model: str | None = None
    pollinations_video_model: str = "google/veo-3.1-fast"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KYRO_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
