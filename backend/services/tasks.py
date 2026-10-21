"""Tâches de génération en arrière-plan (image / vidéo).

La génération longue est lancée avec `asyncio.create_task` : le client reçoit
immédiatement un `generation_id` et poll l'état via /api/generations/{id}.
En cas d'échec : statut FAILED + REMBOURSEMENT AUTOMATIQUE des crédits.
(Pour un déploiement multi-instances, remplacer par Celery/RQ + Redis — voir README.)
"""

import asyncio
import logging
import uuid
from pathlib import Path

from .. import credits as credit_service
from . import ai as ai
from ..config import settings
from ..database import SessionLocal
from ..models import AuditLog, Generation, utcnow

logger = logging.getLogger("kyro.tasks")

MEDIA_ROOT = Path(settings.media_dir)


def save_media(content: bytes, extension: str, prefix: str) -> str:
    """Enregistre un média généré et retourne l'URL publique (/media/...)."""
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{uuid.uuid4().hex}.{extension.lstrip('.')}"
    (MEDIA_ROOT / name).write_bytes(content)
    return f"/media/{name}"


async def run_generation(generation_id: str) -> None:
    """Exécute une génération PENDING : succès → enregistrement du média ; échec → remboursement."""
    db = SessionLocal()
    try:
        gen = db.get(Generation, generation_id)
        if gen is None or gen.status != "PENDING":
            return

        gen.status = "RUNNING"
        db.commit()

        try:
            if gen.kind == "IMAGE":
                content, ext = await ai.generate_image(gen.prompt)
                gen.media_url = save_media(content, ext, "image")
                gen.provider = ai.image_provider_label()
            elif gen.kind == "VIDEO":
                content, ext = await ai.generate_video(gen.prompt)
                gen.media_url = save_media(content, ext, "video")
                gen.provider = ai.video_provider_label()
            else:
                raise ai.ProviderError(f"Type de génération non pris en charge : {gen.kind}")

            gen.status = "SUCCESS"
            gen.completed_at = utcnow()
            db.commit()

        except Exception as exc:  # noqa: BLE001 — toute erreur = échec + remboursement
            logger.exception("Échec de la génération %s", generation_id)
            db.rollback()
            gen = db.get(Generation, generation_id)
            gen.status = "FAILED"
            gen.error = str(exc)
            gen.completed_at = utcnow()
            db.add(AuditLog(level="ERROR", message=f"Génération {generation_id} échouée", context={"kind": gen.kind, "error": str(exc)[:500]}))
            db.commit()
            # Remboursement automatique (idempotent)
            credit_service.refund_credits(db, gen.user_id, gen.credits_cost, generation_id)
    except Exception:  # noqa: BLE001
        logger.exception("Erreur fatale dans run_generation(%s)", generation_id)
        db.rollback()
    finally:
        db.close()


def launch(generation_id: str) -> None:
    """Lance la tâche d'arrière-plan (à appeler après le commit de la génération)."""
    asyncio.create_task(run_generation(generation_id))


async def shutdown() -> None:
    """Annule proprement les tâches en cours à l'arrêt du serveur (best effort)."""
    for task in asyncio.all_tasks():
        if task.get_coro().__qualname__.startswith("run_generation"):
            task.cancel()
