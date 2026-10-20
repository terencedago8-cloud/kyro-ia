"""Schémas Pydantic (validation des entrées de l'API)."""
from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------

class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_suspended: bool
    created_at: str

    @classmethod
    def from_user(cls, u) -> "UserOut":
        return cls(
            id=u.id, email=u.email, username=u.username, role=u.role,
            is_suspended=u.is_suspended, created_at=u.created_at.isoformat(),
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


# ---------- Générations ----------

class PromptIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = None


class GenerationOut(BaseModel):
    id: str
    kind: str
    status: str
    prompt: str
    text: str | None
    media_url: str | None
    provider: str | None
    credits_cost: int
    error: str | None
    created_at: str
    completed_at: str | None

    @classmethod
    def from_gen(cls, g) -> "GenerationOut":
        return cls(
            id=g.id, kind=g.kind, status=g.status, prompt=g.prompt, text=g.text,
            media_url=g.media_url, provider=g.provider, credits_cost=g.credits_cost,
            error=g.error, created_at=g.created_at.isoformat(),
            completed_at=g.completed_at.isoformat() if g.completed_at else None,
        )


class ChatOut(BaseModel):
    reply: str
    conversation_id: str
    generation: GenerationOut
    credits: dict


# ---------- Admin ----------

class AdminCreditIn(BaseModel):
    action: str = Field(pattern=r"^(add|remove|set|reset)$")
    amount: int | None = Field(default=None, ge=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=255)


class AdminGrantAllIn(BaseModel):
    amount: int = Field(gt=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=255)


class AdminUserPatch(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(USER|ADMIN)$")
    is_suspended: bool | None = None


class AdminSettingsPut(BaseModel):
    settings: dict
