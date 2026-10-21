"""Test des fournisseurs IA RÉELS — exécuté contre http://127.0.0.1:8000 (serveur lancé).

Pour chaque fonction, ce test vérifie le contrat du cahier des charges :

  • fournisseur disponible → génération RÉELLE (réponse non vide / fichier image)
    et déduction EXACTE de 3 crédits ;
  • fournisseur en échec (dont quota gratuit atteint) → remboursement intégral ;
  • aucun fournisseur → 503 explicatif, JAMAIS de contenu simulé.

Le repli gratuit Pollinations limite le débit (~1 texte/30 s, ~1 image/45 s par IP) :
les attentes ci-dessous sont volontaires afin de tester le cas nominal, et un
dépassement de quota reste couvert par les invariants de remboursement.

    python tests/test_providers.py
"""

import re
import time

import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=300)
ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        print(f"  [ÉCHEC] {name} {extra}")


def balance(headers) -> int:
    return c.get("/api/me", headers=headers).json()["credits"]["balance"]


# ---------------------------------------------------------------- fournisseurs

print("== 1. État des fournisseurs (aucune clé exposée) ==")
r = c.get("/api/providers")
check("GET /api/providers → 200", r.status_code == 200, f"({r.status_code})")
prov = r.json() if r.status_code == 200 else {}
blob = str(prov)
secret = re.search(r"(sk-[A-Za-z0-9_\-]{16,}|r8_[A-Za-z0-9]{16,}|gsk_[A-Za-z0-9]{16,})", blob)
check("Aucune clé secrète dans la réponse", secret is None,
      f"({secret.group(0)[:14]}…)" if secret else "")
check("4 fonctions décrites (chat, code, image, video)", {"chat", "code", "image", "video"} <= set(prov),
      f"({sorted(prov)})")
check("Chaque état est un booléen 'configured'",
      all(isinstance(prov.get(k, {}).get("configured"), bool) for k in ("chat", "code", "image", "video")))
check("Vidéo : indisponible tant qu'aucune clé n'existe (pas de fausse promesse)",
      prov.get("video", {}).get("configured") is False or bool(prov.get("video", {}).get("note")))

# ---------------------------------------------------------------- compte de test

print("== 2. Inscription ==")
ts = int(time.time())
r = c.post("/api/auth/register", json={
    "email": f"prov_{ts}@kyro.ai", "username": f"p{ts % 100000}", "password": "Motdepasse123",
})
check("POST /api/auth/register → 201", r.status_code == 201, f"({r.status_code}: {r.text[:150]})")
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# ---------------------------------------------------------------- chat

print("== 3. Chat IA ==")
avant = balance(H)
r = c.post("/api/chat", headers=H, json={"message": "Réponds exactement : KYRO OK"})
apres = balance(H)
if prov.get("chat", {}).get("configured"):
    if r.status_code == 200:
        reply = r.json().get("reply", "")
        check("Réponse du vrai modèle (non vide)", len(reply.strip()) > 0, f"({r.text[:150]})")
        check("Déduction exacte = 3 crédits", apres == avant - 3, f"(avant={avant} après={apres})")
    else:
        detail = str(r.json().get("detail", ""))
        check(f"Échec fournisseur ({r.status_code}) → remboursement intégral", apres == avant,
              f"(avant={avant} après={apres})")
        check("Message en français annonçant le remboursement",
              "rembours" in detail.lower() or "fournisseur" in detail.lower(), f"({detail[:140]})")
else:
    check("503 message explicatif", r.status_code == 503 and "fournisseur" in str(r.json().get("detail", "")).lower(),
          f"({r.status_code}: {r.text[:160]})")
    check("Aucun crédit débité", apres == avant, f"(avant={avant} après={apres})")

# ---------------------------------------------------------------- code

print("== 4. Code IA ==")
print("   attente 31 s (quota du fournisseur gratuit)")
time.sleep(31)
avant = balance(H)
r = c.post("/api/code", headers=H, json={"prompt": "Écris une fonction Python qui additionne deux nombres."})
apres = balance(H)
if prov.get("code", {}).get("configured"):
    if r.status_code == 200:
        gen = r.json()
        check("Code généré non vide", bool(str(gen.get("text") or "").strip()), f"({r.text[:150]})")
        check("Déduction exacte = 3 crédits", apres == avant - 3, f"(avant={avant} après={apres})")
        check("Fournisseur réellement utilisé enregistré", bool(gen.get("provider")), f"({gen.get('provider')})")
    else:
        check(f"Échec fournisseur ({r.status_code}) → remboursement intégral", apres == avant,
              f"({r.text[:160]})")
else:
    check("503 message explicatif", r.status_code == 503, f"({r.status_code})")
    check("Aucun crédit débité", apres == avant)

# ---------------------------------------------------------------- images

print("== 5. Image IA (génération asynchrone) ==")
print("   attente 46 s (quota image du fournisseur gratuit)")
time.sleep(46)
avant = balance(H)
r = c.post("/api/images", headers=H, json={"prompt": "un renard blanc dans la neige, illustration"})
if prov.get("image", {}).get("configured"):
    check("POST /api/images → 202", r.status_code == 202, f"({r.status_code}: {r.text[:180]})")
    if r.status_code == 202:
        gid = r.json()["generation_id"]
        gen = None
        for _ in range(60):
            g = c.get(f"/api/generations/{gid}", headers=H)
            if g.status_code == 200 and g.json()["status"] in ("SUCCESS", "FAILED"):
                gen = g.json()
                break
            time.sleep(3)
        check("La tâche se termine (SUCCESS ou FAILED)", gen is not None,
              "(délai de 180 s dépassé)" if gen is None else "")
        if gen:
            apres = balance(H)
            if gen["status"] == "SUCCESS":
                check("Fichier image réel servi depuis /media/", bool(gen.get("media_url")), f"({gen})")
                if gen.get("media_url"):
                    m = c.get(gen["media_url"])
                    check("Le fichier est bien une image non vide",
                          m.status_code == 200 and m.headers.get("content-type", "").startswith("image/")
                          and len(m.content) > 1000,
                          f"({m.status_code}, {m.headers.get('content-type')}, {len(m.content)} o)")
                check("Déduction exacte = 3 crédits", apres == avant - 3, f"(avant={avant} après={apres})")
            else:
                check("Échec → remboursement intégral", apres == avant,
                      f"(avant={avant} après={apres}, erreur: {str(gen.get('error'))[:140]})")
                check("Erreur explicite enregistrée (jamais de fausse image)", bool(gen.get("error")))
else:
    check("503 image non configurée", r.status_code == 503, f"({r.status_code})")
    check("Aucun crédit débité", balance(H) == avant)

# ---------------------------------------------------------------- vidéos

print("== 6. Vidéo IA ==")
avant = balance(H)
r = c.post("/api/videos", headers=H, json={"prompt": "un oiseau qui vole au coucher du soleil"})
apres = balance(H)
if prov.get("video", {}).get("configured"):
    check("POST /api/videos → 202 (clé configurée)", r.status_code == 202, f"({r.status_code}: {r.text[:180]})")
    check("Déduction exacte = 3 crédits", apres == avant - 3, f"(avant={avant} après={apres})")
else:
    check("503 : la vidéo exige une clé (message explicite)",
          r.status_code == 503 and "KYRO_VIDEO_API_KEY" in str(r.json().get("detail", "")),
          f"({r.status_code}: {r.text[:200]})")
    check("Aucun crédit débité", apres == avant, f"(avant={avant} après={apres})")

# ---------------------------------------------------------------- bilan

print(f"\nRÉSULTAT : {ok} OK / {fail} ÉCHEC sur {ok + fail} vérifications")
raise SystemExit(1 if fail else 0)
