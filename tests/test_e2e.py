"""Test de bout en bout KYRO AI — exécuté contre http://127.0.0.1:8000 (serveur lancé)."""
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30)
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


print("== 1. Santé ==")
r = c.get("/api/health")
check("GET /api/health", r.status_code == 200 and r.json()["status"] == "ok")

print("== 2. Frontend ==")
r = c.get("/")
check("Page d'accueil servie", r.status_code == 200 and "KYRO" in r.text)

print("== 3. Inscription ==")
email = f"test_{int(time.time())}@kyro.ai"
r = c.post("/api/auth/register", json={"email": email, "username": f"k{int(time.time())%100000}", "password": "Motdepasse123"})
check("POST /api/auth/register → 201", r.status_code == 201, f"({r.status_code}: {r.text[:200]})")
token = r.json().get("access_token", "")
H = {"Authorization": f"Bearer {token}"}
check("Solde initial = 200 crédits", c.get("/api/me", headers=H).json()["credits"]["balance"] == 200)

print("== 4. Sécurité inscription (rôle ADMIN impossible) ==")
r2 = c.post("/api/auth/register", json={"email": "admin_fake@kyro.ai", "username": "fakeadmin", "password": "Motdepasse123", "role": "ADMIN"})
check(" champ 'role' ignoré (reste USER)", r2.json()["user"]["role"] == "USER")

print("== 5. Connexion & mauvais mot de passe ==")
r = c.post("/api/auth/login", json={"email": email, "password": "faux"})
check("Mauvais mot de passe → 401", r.status_code == 401)
r = c.post("/api/auth/login", json={"email": email, "password": "Motdepasse123"})
check("Bonne connexion → 200 + jeton", r.status_code == 200 and "access_token" in r.json())

print("== 6. Chat sans fournisseur configuré → 503 + remboursement ==")
before = c.get("/api/me", headers=H).json()["credits"]["balance"]
r = c.post("/api/chat", headers=H, json={"message": "Bonjour Kyro !"})
check("503 message explicatif (pas de fausse génération)", r.status_code == 503 and "fournisseur" in r.json()["detail"].lower(), f"({r.status_code}: {r.text[:200]})")
after = c.get("/api/me", headers=H).json()["credits"]["balance"]
check("Crédits remboursés (solde inchangé)", before == after, f"(avant={before} après={after})")

print("== 7. Images sans fournisseur → 503 ==")
r = c.post("/api/images", headers=H, json={"prompt": "un chat dans l'espace"})
check("503 image non configurée", r.status_code == 503, f"({r.status_code})")

print("== 8. Blocage solde insuffisant (402) ==")
r = c.get("/api/admin/stats", headers=H)
check("Route admin bloquée pour USER → 403", r.status_code == 403, f"({r.status_code})")

print("== 9. Histoire / galerie / profil ==")
check("GET /api/generations", c.get("/api/generations", headers=H).status_code == 200)
check("GET /api/gallery", c.get("/api/gallery", headers=H).status_code == 200)
check("GET /api/me/credits/history", c.get("/api/me/credits/history", headers=H).status_code == 200)
check("GET /api/conversations", c.get("/api/conversations", headers=H).status_code == 200)

print("== 10. Jeton invalide ==")
check("401 sans jeton", c.get("/api/me").status_code == 401)
check("401 avec jeton bidon", c.get("/api/me", headers={"Authorization": "Bearer bidon"}).status_code == 401)

print("== 11. Rate-limit connexion ==")
codes = [c.post("/api/auth/login", json={"email": email, "password": "faux"}).status_code for _ in range(6)]
check("6 échecs → 429 (blocage)", 429 in codes, f"({codes})")

print(f"\n{'='*40}\nRÉSULTAT : {ok} réussis, {fail} échec(s)")
sys.exit(1 if fail else 0)
