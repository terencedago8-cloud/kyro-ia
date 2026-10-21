"""Connecteurs IA réels — aucune génération simulée, aucun contenu factice.

Choix automatique du fournisseur, pour chaque fonction (du plus prioritaire au moins) :

    Chat / Code
      1. Clé compatible OpenAI   KYRO_CHAT_API_BASE + KYRO_CHAT_API_KEY (OpenAI, Groq, Mistral…)
      2. Clé Pollinations        KYRO_POLLINATIONS_KEY (une seule clé gratuite pour tout)
      3. Repli GRATUIT sans clé  text.pollinations.ai  (KYRO_FREE_AI=true, activé par défaut)

    Images
      1. Clé compatible OpenAI   KYRO_IMAGE_API_BASE + KYRO_IMAGE_API_KEY
      2. Clé Pollinations        KYRO_POLLINATIONS_KEY
      3. Repli GRATUIT sans clé  image.pollinations.ai (KYRO_FREE_AI=true, activé par défaut)

    Vidéos — aucun repli gratuit n'existe : une clé est indispensable
      1. Clé Pollinations sk_… → KYRO_POLLINATIONS_KEY (gratuite : pollen des quêtes)
      2. Clé Replicate    r8_…  → KYRO_VIDEO_API_KEY (+ KYRO_VIDEO_MODEL)
      La vidéo demande une tâche asynchrone (202 → /v1/jobs) : la connexion n'est
      jamais maintenue ouverte pendant la génération, ce qui protège des coupures
      de proxy ; repli synchrone si le serveur ne propose pas ce mode.

Garanties du cahier des charges :
  • aucun fournisseur disponible → ProviderNotConfigured → 503 en français, AVANT toute
    déduction de crédits, et JAMAIS de génération simulée ;
  • fournisseur en erreur (dont quota de débit atteint) → ProviderError → 502 + remboursement
    automatique des crédits assuré par les routeurs / la tâche de fond.
"""

import asyncio
import base64
from urllib.parse import quote

import httpx

from ..config import settings


class ProviderNotConfigured(Exception):
    """Aucun fournisseur IA disponible pour cette fonctionnalité."""


class ProviderError(Exception):
    """Erreur renvoyée par le fournisseur IA (échec → crédits remboursés)."""


# ---------- Sélection du fournisseur ----------

def _own_chat() -> tuple[str, str, str] | None:
    """(base, clé, modèle) si l'administrateur a fourni son propre fournisseur de texte."""
    if settings.chat_api_base and settings.chat_api_key:
        return settings.chat_api_base.rstrip("/"), settings.chat_api_key, settings.chat_model
    return None


def _own_image() -> tuple[str, str, str] | None:
    """(base, clé, modèle) si l'administrateur a fourni son propre fournisseur d'images."""
    if settings.image_api_base and settings.image_api_key:
        return settings.image_api_base.rstrip("/"), settings.image_api_key, settings.image_model
    return None


def pollinations_key() -> str | None:
    """Clé Pollinations unique (chat + images + vidéos) si elle est renseignée."""
    return (settings.pollinations_key or "").strip() or None


def _pollinations_model(name: str | None, default_prefix: str = "openai/") -> str | None:
    """Pollinations attend « publisher/modèle » : accepte aussi « gpt-4o-mini »."""
    value = (name or "").strip()
    if not value:
        return None
    return value if "/" in value else f"{default_prefix}{value}"


def _video_target() -> tuple[str, str, str] | None:
    """(fournisseur, clé, modèle) pour une vidéo, ou None si non disponible."""
    key = (settings.video_api_key or "").strip()
    if key.startswith("sk_"):
        return "pollinations", key, settings.pollinations_video_model
    if key:
        # Replicate impose un modèle explicite (ex : minimax/video-01)
        return ("replicate", key, settings.video_model) if settings.video_model else None
    free_key = pollinations_key()
    if free_key:
        return "pollinations", free_key, settings.pollinations_video_model
    return None


def chat_configured() -> bool:
    return bool(_own_chat()) or bool(pollinations_key()) or settings.free_ai


def image_configured() -> bool:
    return bool(_own_image()) or bool(pollinations_key()) or settings.free_ai


def video_configured() -> bool:
    return _video_target() is not None


def _chat_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur de chat IA n'est disponible sur le serveur. "
        "L'administrateur doit ajouter KYRO_CHAT_API_KEY (+ KYRO_CHAT_API_BASE) ou "
        "KYRO_POLLINATIONS_KEY, ou bien réactiver le repli gratuit (KYRO_FREE_AI=true), "
        "puis redéployer. Aucun crédit n'a été débité."
    )


def _image_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur d'images IA n'est disponible sur le serveur. "
        "L'administrateur doit ajouter KYRO_IMAGE_API_KEY (+ KYRO_IMAGE_API_BASE) ou "
        "KYRO_POLLINATIONS_KEY, ou bien réactiver le repli gratuit (KYRO_FREE_AI=true), "
        "puis redéployer. Aucun crédit n'a été débité."
    )


def _video_not_configured() -> ProviderNotConfigured:
    return ProviderNotConfigured(
        "Aucun fournisseur de vidéos IA n'est configuré : la vidéo n'a pas de service "
        "gratuit sans clé. L'administrateur doit renseigner KYRO_POLLINATIONS_KEY "
        "(clé gratuite « sk_… » obtenue sur https://enter.pollinations.ai/keys, "
        "le pollen des quêtes est offert) ou KYRO_VIDEO_API_KEY (clé Replicate « r8_… » "
        "avec KYRO_VIDEO_MODEL), puis redéployer. Aucun crédit n'a été débité."
    )


# ---------- Libellés / état (jamais de clé à l'intérieur) ----------

def chat_provider_label() -> str:
    own = _own_chat()
    if own:
        return f"openai-compatible:{own[2]}"
    if pollinations_key():
        return f"pollinations:{_pollinations_model(settings.pollinations_chat_model) or settings.pollinations_chat_model}"
    return "pollinations-free" if settings.free_ai else "non configuré"


def image_provider_label() -> str:
    own = _own_image()
    if own:
        return f"openai-images:{own[2]}"
    if pollinations_key():
        return "pollinations-image"
    return "pollinations-free" if settings.free_ai else "non configuré"


def video_provider_label() -> str:
    target = _video_target()
    if target is None:
        return "non configuré"
    return f"{target[0]}:{target[2]}"


def available() -> dict:
    """État des fournisseurs IA pour le panneau admin et GET /api/providers.

    Aucune clé secrète n'y figure jamais — uniquement des booléens, des libellés
    de modèle et les noms de variables à renseigner.
    """
    chat_own, image_own = _own_chat(), _own_image()
    keyed = bool(pollinations_key())
    chat_free = chat_configured() and not chat_own and not keyed
    image_free = image_configured() and not image_own and not keyed
    video_target = _video_target()

    if chat_free:
        chat_note = ("Repli gratuit sans clé, débit limité (~1 requête toutes les 30 s par serveur). "
                     "Ajoutez une clé pour lever cette limite.")
    elif not chat_configured():
        chat_note = "Aucun fournisseur : renseignez KYRO_CHAT_API_KEY ou KYRO_POLLINATIONS_KEY."
    else:
        chat_note = None

    if image_free:
        image_note = ("Repli gratuit sans clé, débit limité (~1 image toutes les 45 s par serveur). "
                      "Ajoutez une clé pour lever cette limite.")
    elif not image_configured():
        image_note = "Aucun fournisseur : renseignez KYRO_IMAGE_API_KEY ou KYRO_POLLINATIONS_KEY."
    else:
        image_note = None

    if image_own:
        image_model = image_own[2]
    elif keyed:
        image_model = settings.pollinations_image_model or "auto (Pollinations)"
    elif image_configured():
        image_model = None  # modèle unique imposé par l'API classique gratuite
    else:
        image_model = settings.image_model

    text_block = {
        "configured": chat_configured(),
        "provider": chat_provider_label(),
        "model": chat_own[2] if chat_own else (settings.pollinations_chat_model if keyed else settings.free_chat_model),
        "free": chat_free,
        "note": chat_note,
        "env": ["KYRO_CHAT_API_BASE", "KYRO_CHAT_API_KEY", "KYRO_CHAT_MODEL", "KYRO_POLLINATIONS_KEY"],
    }

    return {
        "chat": dict(text_block),
        "code": dict(text_block),
        "image": {
            "configured": image_configured(),
            "provider": image_provider_label(),
            "model": image_model,
            "free": image_free,
            "note": image_note,
            "env": ["KYRO_IMAGE_API_BASE", "KYRO_IMAGE_API_KEY", "KYRO_IMAGE_MODEL", "KYRO_POLLINATIONS_KEY"],
        },
        "video": {
            "configured": video_configured(),
            "provider": video_provider_label(),
            "model": video_target[2] if video_target else settings.video_model,
            "free": False,
            "note": None if video_configured() else (
                "La vidéo exige une clé (aucun service gratuit anonyme n'existe) : créez une "
                "clé gratuite sur https://enter.pollinations.ai/keys puis ajoutez "
                "KYRO_POLLINATIONS_KEY — ou une clé Replicate avec KYRO_VIDEO_API_KEY."
            ),
            "env": ["KYRO_VIDEO_API_KEY", "KYRO_VIDEO_MODEL", "KYRO_POLLINATIONS_KEY"],
        },
    }


# ---------- Erreurs traduites en français ----------

def _failure(r: httpx.Response, what: str) -> ProviderError:
    """Transforme une réponse d'erreur fournisseur en message français exploitable.

    Le cas 402 + Retry-After correspond au quota de débit du service gratuit :
    c'est un échec honnête (donc remboursé), jamais une fausse génération.
    """
    if r.status_code == 402:
        retry = r.headers.get("retry-after", "")
        pause = f" Réessayez dans {retry} s." if retry.strip().isdigit() else " Réessayez plus tard."
        return ProviderError(f"Le service {what} est saturé : quota de débit gratuit atteint.{pause}")
    try:
        detail = " ".join(r.text[:300].split())
    except Exception:  # noqa: BLE001 — réponse binaire illisible
        detail = "réponse illisible"
    return ProviderError(f"Réponse {r.status_code} du service {what} : {detail}")


def _looks_like_mp4(content: bytes) -> bool:
    return len(content) > 12 and content[4:8] == b"ftyp"


def _media_ext(content_type: str) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    return {"image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}.get(ctype, "png")


SYSTEM_PROMPT_CHAT = (
    "Tu es Kyro AI, une intelligence artificielle utile, précise et sympathique. "
    "Tu réponds TOUJOURS en français, sauf si l'utilisateur écrit dans une autre langue."
)

SYSTEM_PROMPT_CODE = (
    "Tu es Kyro AI, un expert en programmation. Tu écris du code propre, commenté et fonctionnel. "
    "Réponds en français. Donne le code dans un bloc de code avec le nom du langage, "
    "puis une explication courte de ce que fait le code."
)


# ---------- CHAT / CODE ----------

def _chat_target() -> tuple[str, str | None, str] | None:
    """(url complète, clé optionnelle, modèle) du fournisseur de texte retenu."""
    own = _own_chat()
    if own:
        base, key, model = own
        return f"{base}/chat/completions", key, model
    key = pollinations_key()
    if key:
        model = _pollinations_model(settings.pollinations_chat_model) or "openai/gpt-4o-mini"
        return f"{settings.pollinations_api_base.rstrip('/')}/v1/chat/completions", key, model
    if settings.free_ai:
        return settings.free_chat_endpoint, None, settings.free_chat_model
    return None


async def _post_chat(
    messages: list[dict],
    *,
    temperature: float,
    timeout: float,
    what: str,
) -> str:
    """POST un appel /chat/completions sur le fournisseur retenu, renvoie la réponse texte."""
    target = _chat_target()
    if target is None:
        raise _chat_not_configured()
    url, key, model = target
    payload = {"model": model, "messages": messages, "temperature": temperature}
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le service {what} : {e}") from e

    if r.status_code != 200:
        raise _failure(r, what)
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        raise ProviderError(f"Réponse inattendue du service {what}.") from e


async def chat_complete(messages: list[dict]) -> str:
    """`messages` = [{"role": "user"|"assistant", "content": ...}, ...] → réponse texte."""
    return await _post_chat(
        [{"role": "system", "content": SYSTEM_PROMPT_CHAT}] + messages[-20:],
        temperature=0.7,
        timeout=120,
        what="de chat",
    )


async def generate_code(prompt: str) -> str:
    """Génération de code : même fournisseur que le chat, prompt système dédié."""
    return await _post_chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT_CODE},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        timeout=180,
        what="de code",
    )


# ---------- IMAGES ----------

async def _download_image(url: str, params: dict, headers: dict) -> tuple[bytes, str]:
    """GET une URL de génération d'image (Pollinations) → (octets, extension)."""
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        try:
            r = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur d'images : {e}") from e

    if r.status_code != 200:
        raise _failure(r, "d'images")
    content_type = r.headers.get("content-type", "")
    if not content_type.lower().startswith("image/"):
        raise ProviderError(
            f"Le fournisseur d'images n'a pas renvoyé d'image "
            f"({content_type.split(';')[0] or 'type inconnu'})."
        )
    return r.content, _media_ext(content_type)


async def generate_image(prompt: str) -> tuple[bytes, str]:
    """Retourne (octets de l'image, extension) — jamais d'image de remplacement factice."""
    if not image_configured():
        raise _image_not_configured()

    own = _own_image()
    if own:
        base, key, model = own
        payload = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}
        async with httpx.AsyncClient(timeout=300) as client:
            try:
                r = await client.post(
                    f"{base}/images/generations",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
            except httpx.HTTPError as e:
                raise ProviderError(f"Impossible de joindre le fournisseur d'images : {e}") from e
        if r.status_code != 200:
            raise _failure(r, "d'images")
        try:
            item = (r.json().get("data") or [{}])[0]
        except ValueError as e:
            raise ProviderError("Réponse inattendue du fournisseur d'images.") from e
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"]), "png"
        if item.get("url"):
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                dl = await client.get(item["url"])
            if dl.status_code != 200:
                raise ProviderError("Impossible de télécharger l'image générée.")
            return dl.content, _media_ext(dl.headers.get("content-type", "image/png"))
        raise ProviderError("Réponse inattendue du fournisseur d'images.")

    # Repli Pollinations : le fournisseur renvoie directement l'image (JPEG).
    key = pollinations_key()
    if key:
        url = f"{settings.pollinations_api_base.rstrip('/')}/image/{quote(prompt, safe='')}"
        params: dict = {"width": 1024, "height": 1024}
        if settings.pollinations_image_model:
            params["model"] = settings.pollinations_image_model
        return await _download_image(url, params, {"Authorization": f"Bearer {key}"})

    if settings.free_ai:
        url = f"{settings.free_image_endpoint.rstrip('/')}/{quote(prompt, safe='')}"
        return await _download_image(url, {"width": 1024, "height": 1024, "nologo": "true"}, {})

    raise _image_not_configured()


# ---------- VIDÉOS ----------

async def _video_replicate(
    prompt: str, key: str, model: str, poll_seconds: int, timeout_seconds: int
) -> tuple[bytes, str]:
    """Replicate : création de la prédiction, puis polling jusqu'à succès."""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    base = settings.video_api_base.rstrip("/")
    endpoint = f"{base}/models/{model}/predictions"

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(endpoint, headers=headers, json={"input": {"prompt": prompt}})
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur de vidéos : {e}") from e
        if r.status_code not in (200, 201):
            raise _failure(r, "de vidéos")
        prediction = r.json()
        prediction_url = prediction.get("urls", {}).get("get") or f"{base}/predictions/{prediction['id']}"

        waited = 0
        while waited < timeout_seconds:
            state = prediction.get("status")
            if state == "succeeded":
                output = prediction.get("output")
                video_url = output[0] if isinstance(output, list) else output
                if not video_url:
                    raise ProviderError("Le fournisseur de vidéos n'a renvoyé aucun fichier.")
                dl = await client.get(video_url)
                if dl.status_code != 200:
                    raise ProviderError("Impossible de télécharger la vidéo générée.")
                return dl.content, "mp4"
            if state in ("failed", "canceled"):
                raise ProviderError(
                    f"La génération de vidéo a échoué : {prediction.get('error', 'raison inconnue')}"
                )
            await asyncio.sleep(poll_seconds)
            waited += poll_seconds
            pr = await client.get(prediction_url, headers=headers)
            if pr.status_code != 200:
                raise ProviderError("Erreur lors du suivi de la génération de vidéo.")
            prediction = pr.json()

    raise ProviderError("La génération de vidéo a expiré (délai maximum dépassé).")


def _video_bytes(r: httpx.Response) -> tuple[bytes, str]:
    """Valide qu'une réponse est bien une vidéo (MP4) et la retourne."""
    content_type = r.headers.get("content-type", "")
    if content_type.lower().startswith("video/") or _looks_like_mp4(r.content):
        return r.content, "mp4"
    if "json" in content_type:
        raise ProviderError(f"Le fournisseur de vidéos a répondu : {' '.join(r.text[:300].split())}")
    raise ProviderError("Le fournisseur de vidéos a renvoyé un contenu inattendu.")


async def _wait_video_job(
    client: httpx.AsyncClient,
    response: httpx.Response,
    auth: dict,
    fallback_url: str,
    fallback_params: dict,
    timeout_seconds: int,
) -> tuple[bytes, str]:
    """Suit une tâche asynchrone Pollinations (202) jusqu'au fichier MP4.

    `Prefer: respond-async` évite de maintenir une connexion HTTP ouverte pendant
    toute la génération : un proxy/CDN coupe généralement au-delà de ~100 s, ce qui
    ferait échouer les modèles vidéo les plus lents. Le suivi n'est jamais facturé.
    """
    base = settings.pollinations_api_base.rstrip("/")
    job_id = None
    try:
        job_id = (response.json() or {}).get("id")
    except ValueError:
        pass
    if not job_id:
        location = (response.headers.get("location") or "").rstrip("/")
        job_id = location.rsplit("/", 1)[-1] or None
    if not job_id:
        # Pas d'identifiant exploitable : voie synchrone classique.
        r = await client.get(fallback_url, params=fallback_params, headers=auth)
        if r.status_code != 200:
            raise _failure(r, "de vidéos")
        return _video_bytes(r)

    poll_seconds = 5
    waited = 0
    while waited <= timeout_seconds:
        jr = await client.get(f"{base}/v1/jobs/{job_id}", headers=auth)
        if jr.status_code == 404:
            # Tâche inconnue ou expirée : la génération synchrone donne le même
            # résultat (une requête identique rejoint la même génération, une seule fois facturée).
            r = await client.get(fallback_url, params=fallback_params, headers=auth)
            if r.status_code != 200:
                raise _failure(r, "de vidéos")
            return _video_bytes(r)
        if jr.status_code != 200:
            raise _failure(jr, "de vidéos")
        try:
            job = jr.json() or {}
        except ValueError as e:
            raise ProviderError("Réponse inattendue du suivi de génération vidéo.") from e

        state = str(job.get("status") or "").lower()
        if state in ("succeeded", "success", "completed", "done"):
            result_url = job.get("result_url") or f"{base}/v1/jobs/{job_id}/result"
            dl = await client.get(result_url, headers=auth, timeout=300)
            if dl.status_code != 200:
                raise _failure(dl, "de vidéos")
            return _video_bytes(dl)
        if state in ("failed", "error", "canceled", "cancelled"):
            reason = job.get("error") or job.get("message") or "raison inconnue"
            raise ProviderError(f"La génération de vidéo a échoué : {reason}")

        await asyncio.sleep(poll_seconds)
        waited += poll_seconds

    raise ProviderError("La génération de vidéo a expiré (délai maximum dépassé).")


async def _video_pollinations(prompt: str, key: str, model: str, timeout_seconds: int) -> tuple[bytes, str]:
    """Pollinations : tâche asynchrone (202 → /v1/jobs), avec repli synchrone si besoin."""
    url = f"{settings.pollinations_api_base.rstrip('/')}/video/{quote(prompt, safe='')}"
    params = {"model": model} if model else {}
    auth = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        try:
            r = await client.get(url, params=params, headers={**auth, "Prefer": "respond-async"})
        except httpx.HTTPError as e:
            raise ProviderError(f"Impossible de joindre le fournisseur de vidéos : {e}") from e

        if r.status_code == 202:
            return await _wait_video_job(client, r, auth, url, params, timeout_seconds)
        if r.status_code == 200:
            return _video_bytes(r)

        # 401 (clé refusée) et 402 (quota atteint) sont définitifs : inutile de réessayer.
        if r.status_code not in (401, 402):
            try:
                r = await client.get(url, params=params, headers=auth)
            except httpx.HTTPError as e:
                raise ProviderError(f"Impossible de joindre le fournisseur de vidéos : {e}") from e
            if r.status_code == 200:
                return _video_bytes(r)

        raise _failure(r, "de vidéos")


async def generate_video(prompt: str, poll_seconds: int = 8, timeout_seconds: int = 900) -> tuple[bytes, str]:
    """Génère une vidéo et retourne (octets, extension). Replicate ou Pollinations."""
    target = _video_target()
    if target is None:
        raise _video_not_configured()
    provider, key, model = target
    if provider == "pollinations":
        return await _video_pollinations(prompt, key, model, timeout_seconds)
    return await _video_replicate(prompt, key, model, poll_seconds, timeout_seconds)
