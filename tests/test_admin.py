"""Test de bout en bout du volet ADMINISTRATEUR + renouvellement horaire (serveur requis)."""
import sys
import time
from datetime import timedelta

import httpx

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30)
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        print(f"  [ÉCHEC] {name} {extra}")


# --- Création de l'admin exactement comme scripts/init_admin.py (côté serveur) ---
from backend import credits as credit_service
from backend.database import Base, SessionLocal, engine
from backend.models import User, UserCredit, utcnow
from backend.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()
if not db.query(User).filter(User.email == "admin@test.kyro").first():
    admin = User(email="admin@test.kyro", username="admin_test", password_hash=hash_password("AdminPass123"), role="ADMIN")
    db.add(admin)
    db.flush()
    db.add(UserCredit(user_id=admin.id, balance=200, period_start=utcnow()))
    db.commit()
admin_id = db.query(User).filter(User.email == "admin@test.kyro").first().id
db.close()
print("== 0. Admin créé via la logique serveur ==")

# --- Utilisateur lambda pour les tests ---
u_email = f"user_{int(time.time())}@kyro.ai"
r = c.post("/api/auth/register", json={"email": u_email, "username": f"u{int(time.time())%100000}", "password": "Motdepasse123"})
UH = {"Authorization": f"Bearer {r.json()['access_token']}"}
user_id = r.json()["user"]["id"]

# --- Connexion admin ---
r = c.post("/api/auth/login", json={"email": "admin@test.kyro", "password": "AdminPass123"})
check("Connexion admin → jeton", r.status_code == 200 and "access_token" in r.json())
AH = {"Authorization": f"Bearer {r.json()['access_token']}"}

print("== 1. Routes admin (statistiques, utilisateurs) ==")
r = c.get("/api/admin/stats", headers=AH)
check("GET /api/admin/stats", r.status_code == 200 and "total_users" in r.json(), f"({r.status_code})")
r = c.get("/api/admin/users?search=admin", headers=AH)
check("Recherche utilisateur par pseudo", r.status_code == 200 and any(i["email"] == "admin@test.kyro" for i in r.json()["items"]))
r = c.get(f"/api/admin/users/{user_id}", headers=AH)
check("Fiche utilisateur détaillée", r.status_code == 200 and "credit_history" in r.json())

print("== 2. Gestion des crédits (add / remove / set / reset + raison) ==")
r = c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "add", "amount": 500, "reason": "Test ajout"})
check("Ajout de 500 crédits", r.status_code == 200 and r.json()["balance"] == 700, f"({r.json()})")
r = c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "remove", "amount": 200, "reason": "Test retrait"})
check("Retrait de 200 crédits", r.json()["balance"] == 500)
r = c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "set", "amount": 42, "reason": "Test définition"})
check("Définition du solde à 42", r.json()["balance"] == 42)
r = c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "reset", "reason": "Test réinitialisation"})
check("Réinitialisation → 200", r.json()["balance"] == 200)
r = c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "add", "amount": 10, "reason": ""})
check("Raison obligatoire → rejetée (4xx)", r.status_code in (400, 422), f"({r.status_code})")

print("== 3. Rôles & suspension (permissions strictes) ==")
r = c.patch(f"/api/admin/users/{user_id}", headers=AH, json={"role": "ADMIN"})
check("Promotion en ADMIN", r.status_code == 200 and r.json()["user"]["role"] == "ADMIN")
r = c.patch(f"/api/admin/users/{user_id}", headers=AH, json={"is_suspended": True})
check("Suspension du compte", r.status_code == 200 and r.json()["user"]["is_suspended"] is True)
ru = c.get("/api/me", headers=UH)
check("Suspendu → 403 sur /api/me", ru.status_code == 403, f"({ru.status_code})")
r = c.patch(f"/api/admin/users/{user_id}", headers=AH, json={"is_suspended": False, "role": "USER"})
check("Réactivation + rétrogradation", r.status_code == 200 and r.json()["user"]["role"] == "USER")

print("== 4. Garde-fous administrateur ==")
r = c.patch(f"/api/admin/users/{admin_id}", headers=AH, json={"role": "USER"})
check("Impossible de rétrograder le dernier ADMIN → 400", r.status_code == 400, f"({r.status_code})")
r = c.patch(f"/api/admin/users/{admin_id}", headers=AH, json={"is_suspended": True})
check("Impossible de se suspendre soi-même → 400", r.status_code == 400)
r = c.delete(f"/api/admin/users/{admin_id}", headers=AH)
check("Impossible de se supprimer soi-même → 400", r.status_code == 400)

print("== 5. Paramètres (coûts, renouvellement, features) ==")
r = c.get("/api/admin/settings", headers=AH)
check("GET /api/admin/settings (clés masquées)", r.status_code == 200 and "KYRO_" in str(r.json()["providers"]["chat"]["env"]))
check("Aucune clé API exposée", "api_key" not in str(r.json()).lower() or "sk-" not in str(r.json()))
r = c.put("/api/admin/settings", headers=AH, json={"settings": {"cost.chat": 7}})
check("Modification du coût chat → 7", r.status_code == 200 and r.json()["updated"]["cost.chat"] == 7)
bal_before = c.get("/api/me", headers=UH).json()["credits"]["balance"]
r = c.post("/api/chat", headers=UH, json={"message": "test coût"})
bal_after = c.get("/api/me", headers=UH).json()["credits"]["balance"]
if c.get("/api/providers").json()["chat"]["configured"]:
    check("Nouveau coût chat = 7 crédits (ou remboursement intégral si le fournisseur échoue)",
          (r.status_code == 200 and bal_after == bal_before - 7)
          or (r.status_code != 200 and bal_after == bal_before),
          f"({r.status_code}, {bal_before}→{bal_after})")
else:
    check("Coût vérifié avant fournisseur → 503", r.status_code == 503, f"({r.status_code})")
c.post(f"/api/admin/users/{user_id}/credits", headers=AH, json={"action": "set", "amount": 5, "reason": "reset pour test 402"})
r = c.post("/api/chat", headers=UH, json={"message": "test"})
check("Solde 5 < coût 7 → 402 crédits insuffisants", r.status_code == 402, f"({r.status_code}: {r.text[:120]})")
c.put("/api/admin/settings", headers=AH, json={"settings": {"cost.chat": 3}})
r = c.put("/api/admin/settings", headers=AH, json={"settings": {"features.chat": False}})
check("Désactivation du chat → 503 (fonction désactivée)", c.post("/api/chat", headers=UH, json={"message": "x"}).status_code == 503)
c.put("/api/admin/settings", headers=AH, json={"settings": {"features.chat": True}})
r = c.put("/api/admin/settings", headers=AH, json={"settings": {"inconnu.chat": 5}})
check("Réglage inconnu rejeté → 400 avec détail", r.status_code == 400 and "inconnu.chat" in str(r.json().get("detail", "")), f"({r.status_code})")

print("== 6. Accorder des crédits à tous ==")
r = c.post("/api/admin/credits/all", headers=AH, json={"amount": 25, "reason": "Événement test"})
check("Grant all → 25 crédits chacun", r.status_code == 200 and r.json()["users_granted"] >= 2)

print("== 7. Journaux d'audit ==")
r = c.get("/api/admin/logs", headers=AH)
check("GET /api/admin/logs", r.status_code == 200 and len(r.json()["admin"]) > 0)
r = c.get(f"/api/admin/users/{user_id}/credits/history", headers=AH)
check("Historique de crédits journalisé", r.status_code == 200 and any(i["kind"].startswith("ADMIN") for i in r.json()["items"]))

print("== 8. Suppression de compte (cascades) ==")
r = c.post("/api/auth/register", json={"email": "del@test.kyro", "username": "adel", "password": "Motdepasse123"})
del_id = r.json()["user"]["id"]
r = c.delete(f"/api/admin/users/{del_id}", headers=AH)
check("Suppression → 204", r.status_code == 204)
check("Compte supprimé → plus de connexion", c.post("/api/auth/login", json={"email": "del@test.kyro", "password": "Motdepasse123"}).status_code == 401)

print("== 9. Renouvellement horaire (même déconnecté, non cumulatif) ==")
db = SessionLocal()
from backend.models import UserCredit as UC
credit_row = db.get(UC, user_id)
credit_row.period_start = utcnow() - timedelta(hours=3)   # 3 h de déconnexion
credit_row.balance = 10
db.commit()
db.close()
me = c.get("/api/me", headers=UH).json()
check("Après 3 h de déconnexion → solde remis à 200 (NON cumulé à 600)", me["credits"]["balance"] == 200, f"({me['credits']['balance']})")
check("Compte à rebours cohérent", 0 <= me["credits"]["seconds_until_renewal"] <= 3600)

print(f"\n{'='*40}\nRÉSULTAT ADMIN : {ok} réussis, {fail} échec(s)")
sys.exit(1 if fail else 0)
