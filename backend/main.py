"""KYRO AI — application FastAPI.

Lancement :
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import credits as credit_service
from .bootstrap import bootstrap_admin
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, chat, code, generations, images, profile, videos
from .services import ai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kyro")

renewal_task: asyncio.Task | None = None


async def renewal_loop():
    """Boucle d'arrière-plan : renouvellement horaire automatique pour TOUS les comptes,
    même déconnectés. Tourne toutes les 60 secondes ; le mécanisme dérivé de
    `period_start` garantit le renouvellement même si cette boucle s'arrête."""
    while True:
        try:
            db = SessionLocal()
            try:
                renewed = credit_service.renew_all(db)
                if renewed:
                    logger.info("Renouvellement horaire appliqué à %d compte(s).", renewed)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Erreur dans la boucle de renouvellement.")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global renewal_task
    # 1. Schéma de base (idempotent) — en cas d'indisponibilité de la BDD, on logge
    #    clairement puis on laisse Render relancer le service.
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:  # noqa: BLE001
        logger.exception("Création du schéma impossible — vérifier KYRO_DATABASE_URL.")
        raise

    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)

    # 2. Premier administrateur (uniquement si aucun n'existe, variables serveur).
    try:
        db = SessionLocal()
        try:
            bootstrap_admin(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("Bootstrap administrateur échoué (non bloquant).")

    renewal_task = asyncio.create_task(renewal_loop())
    logger.info("KYRO AI démarré — renouvellement horaire automatique actif.")
    yield
    renewal_task.cancel()
    try:
        await renewal_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="KYRO AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes API ---
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(images.router)
app.include_router(videos.router)
app.include_router(code.router)
app.include_router(generations.router)
app.include_router(profile.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "KYRO AI"}


@app.get("/api/providers")
def providers():
    """Fonctions IA réellement disponibles côté serveur (aucune clé secrète exposée).

    Sert le frontend à afficher honnêtement ce qui est utilisable : une fonction
    indisponible renvoie 503 avec un message explicatif, jamais une fausse génération.
    """
    return ai.available()


# --- Médias générés (images / vidéos) + frontend (dernier : ne pas écraser /api) ---
Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
Path("frontend").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
