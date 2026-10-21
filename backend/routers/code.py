"""Génération de code IA — 3 crédits par demande (configurable)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import credits as credit_service, schemas
from ..services import ai
from ..database import get_db
from ..deps import CreditsRequired, check_prompt_length
from ..models import Generation, utcnow

router = APIRouter(prefix="/api/code", tags=["code"])


@router.post("", response_model=schemas.GenerationOut)
async def generate_code(
    payload: schemas.PromptIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(CreditsRequired("CODE")),
):
    """Génère du code. La demande coûte 3 crédits (déduits côté serveur, une seule fois)."""
    check_prompt_length(db, payload.prompt)
    if not ai.chat_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(ai._chat_not_configured()))

    cost = request.state.credit_cost
    generation_id = uuid.uuid4().hex

    gen = Generation(
        id=generation_id, user_id=user.id, kind="CODE", status="RUNNING",
        prompt=payload.prompt, credits_cost=cost, provider=ai.chat_provider_label(),
    )
    db.add(gen)
    db.commit()

    try:
        credit_service.consume_credits(db, user.id, cost, "CODE", generation_id, "Génération de code")
    except credit_service.InsufficientCredits as e:
        gen.status = "FAILED"
        gen.error = str(e)
        db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e))

    try:
        result = await ai.generate_code(payload.prompt)
    except ai.ProviderNotConfigured as e:
        gen.status, gen.error = "FAILED", str(e)
        db.commit()
        credit_service.refund_credits(db, user.id, cost, generation_id, "Remboursement — fournisseur non configuré")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except ai.ProviderError as e:
        gen.status, gen.error, gen.completed_at = "FAILED", str(e), utcnow()
        db.commit()
        credit_service.refund_credits(db, user.id, cost, generation_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{str(e).rstrip('.')} Crédits remboursés.")

    gen.text = result
    gen.status = "SUCCESS"
    gen.completed_at = utcnow()
    db.commit()
    return schemas.GenerationOut.from_gen(gen)
