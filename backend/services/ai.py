"""Connecteurs IA réels (aucune simulation).

- CHAT   : API compatible OpenAI (OpenAI, Mistral, OpenRouter, Ollama, ...)
- IMAGES : API Images d'OpenAI (gpt-image-1 / dall-e-3)
- VIDÉOS : API Replicate (minimax/video-01, ...)

Si un fournisseur n'est pas configuré, une exception explicative est levée
et l'API répond 503 avec un message en français — aucune fausse génération.
"""

import base64
import asyncio
import httpx

from ..config import settings


class ProviderNotConfigured(Exception):
    """Aucun fournisseur IA configuré pour cette fonctionnalité."""


class ProviderError(Exception):
    """Erreur renvoyée par le fournisseur IA."""


# ---------- Configuration ----------

def chat_configured() -> bool:
    return bool(settings.chat_api_base and settings.chat_api_key)


def image_configured() -> bool:
    return bool(settings.image_api_base and settings.image_api_key)


def video_configured() -> bool:
    return bool(settings.video_api_key and settings.video_model)


def _chat_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur de chat IA n'est configuré sur le serveur. "
        "L'administrateur doit renseigner KYRO_CHAT_API_BASE et KYRO_CHAT_API_KEY dans le fichier .env, "
        "puis redémarrer le serveur."
    )


def _image_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur d'images IA n'est configuré sur le serveur. "
        "L'administrateur doit renseigner KYRO_IMAGE_API_BASE et KYRO_IMAGE_API_KEY dans le fichier .env, "
        "puis redémarrer le serveur."
    )


def _video_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur de vidéos IA n'est configuré sur le serveur. "
        "L'administrateur doit renseigner KYRO_VIDEO_API_KEY et KYRO_VIDEO_MODEL (ex: minimax/video-01) "
        "dans le fichier .env, puis redémarrer le serveur."
    )


SYSTEM_PROMPT_CHAT = (
    "Tu es Kyro AI, une intelligence artificielle utile, précise et sympathique. "
    "Tu réponds TOUJOURS en français, sauf si l'utilisateur écrit dans une autre langue."
)

SYSTEM_PROMPT_CODE = (
    "Tu es Kyro AI, un expert en programmation. Tu écris du code propre, commenté et fonctionnel. "
    "Réponds en français. Donne le code dans un bloc de code avec le nom du langage, "
    "puis une explication courte de ce que fait le code."
)


# ---------- CHAT ----------

async def chat_complete(messages: list[dict]) -> str:
    """`messages` = [{"role": "user"|"assistant", "content": ...}, ...] → réponse texte."""
    if not chat_configured():
        raise _chat_not_configured()

    payload = {
        "model": settings.chat_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT_CHAT}] + messages[-20:],
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"{settings.chat_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json=payload,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur de chat : {e}") from e
    if r.status_code != 200:
        raise ProviderError(f"Le fournisseur de chat a répondu {r.status_code} : {r.text[:400]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as e:
        raise ProviderError("Réponse inattendue du fournisseur de chat.") from e


async def generate_code(prompt: str) -> str:
    """Génération de code via le même fournisseur de chat, avec un prompt système dédié."""
    if not chat_configured():
        raise _chat_not_configured()
    payload = {
        "model": settings.chat_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_CODE},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.post(
                f"{settings.chat_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json=payload,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur de code : {e}") from e
    if r.status_code != 200:
        raise ProviderError(f"Le fournisseur de code a répondu {r.status_code} : {r.text[:400]}")
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as e:
        raise ProviderError("Réponse inattendue du fournisseur de code.") from e


# ---------- IMAGES ----------

async def generate_image(prompt: str) -> tuple[bytes, str]:
    """Retourne (octets de l'image, extension)."""
    if not image_configured():
        raise _image_not_configured()
    payload = {"model": settings.image_model, "prompt": prompt, "n": 1, "size": "1024x1024"}
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            r = await client.post(
                f"{settings.image_api_base.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {settings.image_api_key}"},
                json=payload,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur d'images : {e}") from e
    if r.status_code != 200:
        raise ProviderError(f"Le fournisseur d'images a répondu {r.status_code} : {r.text[:400]}")
    data = r.json()
    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), "png"
    if item.get("url"):
        async with httpx.AsyncClient(timeout=180) as client:
            dl = await client.get(item["url"])
        if dl.status_code != 200:
            raise ProviderError("Impossible de télécharger l'image générée.")
        return dl.content, "png"
    raise ProviderError("Réponse inattendue du fournisseur d'images.")


# ---------- VIDÉOS (Replicate) ----------

async def generate_video(prompt: str, poll_seconds: int = 8, timeout_seconds: int = 900) -> tuple[bytes, str]:
    """Génère une vidéo via Replicate : création de la prédiction, puis polling jusqu'à succès.

    Retourne (octets de la vidéo, extension).
    """
    if not video_configured():
        raise _video_not_configured()

    owner_name = settings.video_model  # ex: "minimax/video-01"
    headers = {
        "Authorization": f"Bearer {settings.video_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.video_api_base.rstrip('/')}/models/{owner_name}/predictions"

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(endpoint, headers=headers, json={"input": {"prompt": prompt}})
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur de vidéos : {e}") from e
        if r.status_code not in (200, 201):
            raise ProviderError(f"Le fournisseur de vidéos a répondu {r.status_code} : {r.text[:400]}")
        prediction = r.json()
        prediction_url = prediction.get("urls", {}).get("get") or f"{settings.video_api_base.rstrip('/')}/predictions/{prediction['id']}"

        waited = 0
        while waited < timeout_seconds:
            status = prediction.get("status")
            if status == "succeeded":
                output = prediction.get("output")
                video_url = output[0] if isinstance(output, list) else output
                if not video_url:
                    raise ProviderError("Le fournisseur de vidéos n'a renvoyé aucun fichier.")
                dl = await client.get(video_url)
                if dl.status_code != 200:
                    raise ProviderError("Impossible de télécharger la vidéo générée.")
                return dl.content, "mp4"
            if status in ("failed", "canceled"):
                raise ProviderError(f"La génération de vidéo a échoué : {prediction.get('error', 'raison inconnue')}")
            await asyncio.sleep(poll_seconds)
            waited += poll_seconds
            pr = await client.get(prediction_url, headers=headers)
            if pr.status_code != 200:
                raise ProviderError("Erreur lors du suivi de la génération de vidéo.")
            prediction = pr.json()

    raise ProviderError("La génération de vidéo a expiré (délai maximum dépassé).")
