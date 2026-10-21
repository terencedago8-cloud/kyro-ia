"""Chat IA — 3 crédits par message (configurable). Remboursement si le fournisseur échoue."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import credits as credit_service, schemas
from ..services import ai
from ..database import get_db
from ..deps import CreditsRequired, check_prompt_length
from ..models import Conversation, Generation, Message, utcnow

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=schemas.ChatOut)
async def chat(
    payload: schemas.ChatIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(CreditsRequired("CHAT")),
):
    check_prompt_length(db, payload.message)
    if not ai.chat_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(ai._chat_not_configured()))

    cost = request.state.credit_cost
    generation_id = uuid.uuid4().hex

    # Conversation
    if payload.conversation_id:
        conv = db.get(Conversation, payload.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable.")
    else:
        conv = Conversation(user_id=user.id, title=payload.message[:80])
        db.add(conv)
        db.flush()

    gen = Generation(
        id=generation_id, user_id=user.id, kind="CHAT", status="RUNNING",
        prompt=payload.message, credits_cost=cost, provider=ai.chat_provider_label(),
    )
    db.add(gen)
    db.add(Message(conversation_id=conv.id, role="user", content=payload.message))
    db.commit()

    # Déduction (une seule fois, idempotente)
    try:
        credit_service.consume_credits(db, user.id, cost, "CHAT", generation_id, "Demande au chat IA")
    except credit_service.InsufficientCredits as e:
        gen.status = "FAILED"
        gen.error = str(e)
        db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e))

    # Historique envoyé au modèle
    history = db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc()).limit(20)
    ).scalars().all()
    messages = [{"role": m.role, "content": m.content} for m in reversed(history)]

    try:
        reply = await ai.chat_complete(messages)
    except ai.ProviderNotConfigured as e:
        _fail(db, gen)
        credit_service.refund_credits(db, user.id, cost, generation_id, "Remboursement — fournisseur non configuré")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except ai.ProviderError as e:
        _fail(db, gen)
        credit_service.refund_credits(db, user.id, cost, generation_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{str(e).rstrip('.')} Crédits remboursés.")

    gen.text = reply
    gen.status = "SUCCESS"
    gen.completed_at = utcnow()
    db.add(Message(conversation_id=conv.id, role="assistant", content=reply))
    conv.updated_at = utcnow()
    db.commit()

    snapshot = credit_service.get_balance_snapshot(db, user.id)
    return schemas.ChatOut(
        reply=reply,
        conversation_id=conv.id,
        generation=schemas.GenerationOut.from_gen(gen),
        credits=snapshot,
    )


def _fail(db: Session, gen: Generation) -> None:
    gen.status = "FAILED"
    gen.completed_at = utcnow()
    db.commit()
