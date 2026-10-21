"""Génération d'images IA — 3 crédits par image (configurable), tâche en arrière-plan."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import credits as credit_service, schemas
from ..services import ai, tasks
from ..database import get_db
from ..deps import CreditsRequired, check_prompt_length
from ..models import Generation

router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def generate_image(
    payload: schemas.PromptIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(CreditsRequired("IMAGE")),
):
    """Démarre une génération d'image. L'image coûte 3 crédits (déduits côté serveur, une seule fois)."""
    check_prompt_length(db, payload.prompt)
    if not ai.image_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(ai._image_not_configured()))

    cost = request.state.credit_cost
    generation_id = uuid.uuid4().hex

    gen = Generation(
        id=generation_id, user_id=user.id, kind="IMAGE", status="PENDING",
        prompt=payload.prompt, credits_cost=cost, provider=ai.image_provider_label(),
    )
    db.add(gen)
    db.commit()

    try:
        credit_service.consume_credits(db, user.id, cost, "IMAGE", generation_id, "Génération d'image")
    except credit_service.InsufficientCredits as e:
        gen.status = "FAILED"
        gen.error = str(e)
        db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e))

    tasks.launch(generation_id)
    snapshot = credit_service.get_balance_snapshot(db, user.id)
    return {"generation_id": generation_id, "status": "PENDING", "credits": snapshot}
