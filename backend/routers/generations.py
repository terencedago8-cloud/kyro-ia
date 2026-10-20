"""Historique, suivi des générations (polling), conversations et galerie."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import get_current_user
from ..models import Conversation, Generation, Message, User

router = APIRouter(prefix="/api", tags=["generations"])


@router.get("/generations")
def list_generations(
    kind: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Historique des demandes de l'utilisateur connecté (chat, images, vidéos, code)."""
    q = select(Generation).where(Generation.user_id == user.id)
    if kind:
        q = q.where(Generation.kind == kind.upper())
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(
        q.order_by(Generation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [schemas.GenerationOut.from_gen(g) for g in rows],
    }


@router.get("/generations/{generation_id}")
def get_generation(generation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """État d'une génération (utilisé par le frontend pour suivre les tâches longues)."""
    gen = db.get(Generation, generation_id)
    if gen is None or (gen.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Génération introuvable.")
    return schemas.GenerationOut.from_gen(gen)


@router.get("/gallery")
def gallery(
    kind: str | None = Query(default="IMAGE"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Galerie personnelle : images et vidéos générées avec succès."""
    kinds = [k.strip().upper() for k in (kind or "IMAGE,VIDEO").split(",") if k.strip()]
    q = select(Generation).where(
        Generation.user_id == user.id,
        Generation.status == "SUCCESS",
        Generation.media_url.is_not(None),
    )
    if kinds:
        q = q.where(Generation.kind.in_(kinds))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(
        q.order_by(Generation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [schemas.GenerationOut.from_gen(g) for g in rows]}


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(50)
    ).scalars().all()
    return [
        {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}
        for c in rows
    ]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable.")
    messages = db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
    ).scalars().all()
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages],
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable.")
    db.delete(conv)
    db.commit()
