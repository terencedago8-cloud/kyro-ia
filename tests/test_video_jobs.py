"""Test de la chaîne vidéo Pollinations : suivi de tâche asynchrone et replis.

Aucune clé ni réseau requis : les réponses HTTP sont simulées, ce qui permet de
valider le protocole 202 → /v1/jobs → résultat, le repli synchrone et les erreurs
traduites en français — les mêmes chemins exécutés en production.
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from backend.services import ai  # noqa: E402

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        print(f"  [ÉCHEC] {name} {extra}")


MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64  # octets 4:8 == b"ftyp"
CURRENT: dict = {"client": None}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        if self._json is None:
            raise ValueError("pas de JSON")
        return self._json


class FakeClient:
    """Client httpx simulé : `handler(url, kwargs)` décide de la réponse."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


class FakeAsyncClient:
    """Remplace httpx.AsyncClient dans `_video_pollinations` (contexte async)."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return CURRENT["client"]

    async def __aexit__(self, *args):
        return False


def use(handler) -> FakeClient:
    client = FakeClient(handler)
    CURRENT["client"] = client
    return client


async def run():
    # ---------------------------------------------------------------- 202 → suivi → MP4
    etat = {"jobs": 0}

    def succes(u, kw):
        if "/video/" in u:
            check("requête asynchrone envoyée (Prefer: respond-async)",
                  kw.get("headers", {}).get("Prefer") == "respond-async")
            check("clé envoyée en en-tête Authorization",
                  kw.get("headers", {}).get("Authorization") == "Bearer sk_teste")
            return FakeResponse(202, {"id": "job_abc"})
        if "/v1/jobs/job_abc" in u and not u.endswith("/result"):
            etat["jobs"] += 1
            if etat["jobs"] == 1:
                return FakeResponse(200, {"status": "running"})
            return FakeResponse(200, {"status": "succeeded", "result_url": "https://cdn/result"})
        if u.endswith("/result"):
            return FakeResponse(200, content=MP4, headers={"content-type": "video/mp4"})
        return FakeResponse(500, {"error": "inattendu"})

    client = use(succes)
    content, ext = await ai._video_pollinations("un dragon", "sk_teste", "alibaba/wan-2.2-fast", 60)
    check("202 → tâche suivie jusqu'au MP4", content == MP4 and ext == "mp4", f"({ext}, {len(content)} o)")
    check("état interrogé deux fois (running puis succeeded)", etat["jobs"] == 2)
    check("aucun appel superflu", len(client.calls) == 4, f"({len(client.calls)})")

    # ---------------------------------------------------------------- 200 direct (cache)
    use(lambda u, kw: FakeResponse(200, content=MP4, headers={"content-type": "video/mp4"}))
    content, ext = await ai._video_pollinations("un dragon", "sk_teste", "model", 60)
    check("résultat déjà prêt → 200 renvoyé directement", content == MP4 and ext == "mp4")

    # ---------------------------------------------------------------- Prefer refusé → repli
    def sans_prefer(u, kw):
        if kw.get("headers", {}).get("Prefer"):
            return FakeResponse(400, {"error": "Prefer non pris en charge"})
        return FakeResponse(200, content=MP4, headers={"content-type": "video/mp4"})

    client = use(sans_prefer)
    content, ext = await ai._video_pollinations("un dragon", "sk_teste", "model", 60)
    check("mode asynchrone refusé → repli synchrone", content == MP4, f"({len(client.calls)} appels)")
    check("le repli retente SANS l'en-tête Prefer", len(client.calls) == 2
          and "Prefer" not in client.calls[1][1].get("headers", {}))

    # ---------------------------------------------------------------- 202 sans identifiant
    use(lambda u, kw: FakeResponse(200, content=MP4, headers={"content-type": "video/mp4"}))
    content, ext = await ai._wait_video_job(
        CURRENT["client"], FakeResponse(202, {"autre": 1}),
        {"Authorization": "Bearer k"}, "https://x/video/a", {"model": "m"}, 60,
    )
    check("202 sans identifiant → repli synchrone", content == MP4)

    # ---------------------------------------------------------------- 404 → repli
    def inconnu(u, kw):
        if "/v1/jobs/" in u:
            return FakeResponse(404, {"detail": "tâche inconnue"})
        return FakeResponse(200, content=MP4, headers={"content-type": "video/mp4"})

    client = use(inconnu)
    content, _ = await ai._wait_video_job(
        client, FakeResponse(202, {"id": "job_zzz"}),
        {"Authorization": "Bearer k"}, "https://x/video/a", {"model": "m"}, 60,
    )
    check("tâche inconnue (404) → repli synchrone abouti", content == MP4)
    check("le repli retente une seule fois la génération", len(client.calls) == 2)

    # ---------------------------------------------------------------- échec de la tâche
    use(lambda u, kw: FakeResponse(200, {"status": "failed", "error": "prompt refusé"}))
    try:
        await ai._wait_video_job(
            CURRENT["client"], FakeResponse(202, {"id": "job_e"}),
            {"Authorization": "Bearer k"}, "https://x/video/a", {}, 60,
        )
        check("échec de tâche → ProviderError", False)
    except ai.ProviderError as e:
        check("échec de tâche → ProviderError", "échoué" in str(e) and "prompt refusé" in str(e), str(e))

    # ---------------------------------------------------------------- expiration
    use(lambda u, kw: FakeResponse(200, {"status": "running"}))
    try:
        await ai._wait_video_job(
            CURRENT["client"], FakeResponse(202, {"id": "job_l"}),
            {"Authorization": "Bearer k"}, "https://x/video/a", {}, 0,
        )
        check("délai dépassé → ProviderError explicite", False)
    except ai.ProviderError as e:
        check("délai dépassé → ProviderError explicite", "expiré" in str(e), str(e))

    # ---------------------------------------------------------------- 402 quota
    client = use(lambda u, kw: FakeResponse(402, {"error": "PAID_REQUIRED"},
                                            headers={"retry-after": "30"}))
    try:
        await ai._video_pollinations("un dragon", "sk_teste", "model", 60)
        check("402 → message de quota traduit (remboursement)", False)
    except ai.ProviderError as e:
        check("402 → message de quota traduit (remboursement)",
              "quota de débit" in str(e) and "30" in str(e), str(e))
        check("402 définitif : aucune seconde tentative", len(client.calls) == 1)

    # ---------------------------------------------------------------- 401 clé refusée
    client = use(lambda u, kw: FakeResponse(401, {"error": {"message": "clé invalide"}}))
    try:
        await ai._video_pollinations("un dragon", "sk_teste", "model", 60)
        check("401 → erreur, sans relance (clé définitive)", False)
    except ai.ProviderError as e:
        check("401 → erreur, sans relance (clé définitive)", len(client.calls) == 1, str(e))
        check("le 401 est traduit en français exploitable", "401" in str(e), str(e))

    # ---------------------------------------------------------------- contenu inattendu
    try:
        ai._video_bytes(FakeResponse(200, {"ok": True}, headers={"content-type": "application/json"}))
        check("réponse JSON → ProviderError (jamais de vidéo factice)", False)
    except ai.ProviderError:
        check("réponse JSON → ProviderError (jamais de vidéo factice)", True)


def main():
    original = ai.httpx.AsyncClient
    ai.httpx.AsyncClient = FakeAsyncClient
    try:
        asyncio.run(run())
    finally:
        ai.httpx.AsyncClient = original

    print(f"\n{ok} réussite(s), {fail} échec(s)")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
