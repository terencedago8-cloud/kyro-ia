# ⚡ KYRO AI

**Intelligence artificielle complète avec système de crédits** — chat IA, génération d'images, de vidéos et de code, interface moderne sombre (bleu électrique + violet), panneau d'administration sécurisé.

![Stack](https://img.shields.io/badge/Backend-FastAPI-blue) ![DB](https://img.shields.io/badge/Base-PostgreSQL-336791) ![Front](https://img.shields.io/badge/Frontend-HTML%20%2B%20CSS%2B%20JS-purple)

---

## ✨ Fonctionnalités

| Module | Description |
|---|---|
| 💬 Chat IA | Conversations en français, historique illimité, conversations multiples |
| 🎨 Images IA | Génération d'images via l'API Images OpenAI (gpt-image-1 / dall-e-3) |
| 🎬 Vidéos IA | Génération de vidéos via Replicate (minimax/video-01, …) |
| 💻 Code IA | Code propre et commenté avec explications, tous langages |
| 💰 Crédits | 3 crédits / demande, +200 crédits/heure automatiques, remboursement en cas d'échec |
| 🖼️ Galerie | Galerie personnelle des images et vidéos générées |
| 👑 Admin | Gestion des utilisateurs, crédits, statistiques, paramètres, journaux |

---

## 🏗️ Architecture

```
kyro-ia/
├── backend/
│   ├── main.py              # Application FastAPI + boucle de renouvellement horaire
│   ├── config.py            # Configuration (.env — clés secrètes côté serveur uniquement)
│   ├── database.py          # SQLAlchemy / PostgreSQL
│   ├── models.py            # Modèles : users, user_credits, credit_ledger, generations…
│   ├── security.py          # PBKDF2 (mots de passe), JWT, anti-force-brute
│   ├── credits.py           # ★ Moteur de crédits (déduction idempotente, renouvellement, remboursements, audit)
│   ├── deps.py              # Dépendances : utilisateur courant, rôle ADMIN, limites
│   ├── schemas.py           # Validation Pydantic
│   ├── routers/             # auth, chat, images, videos, code, generations, profile, admin
│   └── services/
│       ├── ai.py            # Connecteurs IA réels (OpenAI-compatible, Images, Replicate)
│       └── tasks.py         # Tâches en arrière-plan + remboursement automatique
├── frontend/                # SPA HTML/CSS/JS (thème sombre, responsive PC & mobile)
├── scripts/init_admin.py    # Création sécurisée du premier administrateur
├── schema.sql               # Schéma PostgreSQL (référence)
├── docker-compose.yml       # PostgreSQL + application
└── Dockerfile
```

---

## 🚀 Installation

### 1. Prérequis

- Python **3.11+**
- PostgreSQL **14+** (ou Docker)

### 2. Base de données

**Avec Docker (recommandé) :**

```bash
docker compose up -d db
```

**Sans Docker :** créez une base manuellement :

```sql
CREATE USER kyro WITH PASSWORD 'kyro';
CREATE DATABASE kyro OWNER kyro;
```

### 3. Configuration

```bash
cp .env.example .env
```

Éditez `.env` : renseignez `KYRO_JWT_SECRET` (chaîne aléatoire longue) et vos clés API.

| Variable | Rôle |
|---|---|
| `KYRO_DATABASE_URL` | Chaîne de connexion PostgreSQL |
| `KYRO_JWT_SECRET` | Secret de signature des jetons (obligatoire, long et aléatoire) |
| `KYRO_CHAT_API_BASE` / `KYRO_CHAT_API_KEY` / `KYRO_CHAT_MODEL` | Chat & code (compatible OpenAI) |
| `KYRO_IMAGE_API_BASE` / `KYRO_IMAGE_API_KEY` / `KYRO_IMAGE_MODEL` | Images |
| `KYRO_VIDEO_API_KEY` / `KYRO_VIDEO_MODEL` | Vidéos (Replicate, ex. `minimax/video-01`) |

> 🔐 **Les clés API ne quittent jamais le serveur** — elles ne sont ni dans le navigateur ni dans le code public. Si un fournisseur n'est pas configuré, l'API renvoie un message explicatif (503) au lieu de simuler une génération.

### 4. Démarrage

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt

uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Les tables sont créées automatiquement au premier démarrage (`create_all`). Ouvrez **http://localhost:8000**.

### 5. Premier administrateur (obligatoire, sécurisé)

Le rôle ADMIN ne peut **pas** être choisi à l'inscription ni modifié par un utilisateur. Il se crée uniquement côté serveur.

**Installation PostgreSQL automatisée** (recommandée — crée le rôle, la base, le schéma puis le premier admin) :

```bash
python -m scripts.setup_postgres
```

Le script lit `.env` (`ADMIN_EMAIL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`) ou demande les valeurs de façon interactive ; le mot de passe est saisi de façon masquée si absent. Aucun admin n'existe ⇒ il est créé, sinon le script le signale et n'écrase rien.

**Alternative manuelle** (base déjà provisionnée) :

```bash
python -m scripts.init_admin
```

---

## 💰 Système de crédits — règles implémentées

| Règle | Implémentation |
|---|---|
| Chat / image / vidéo / code = **3 crédits** chacun | Réglable par l'admin (`/admin/parametres`), défaut 3 |
| **+200 crédits chaque heure**, automatiques | Boucle serveur toutes les 60 s **+** mécanisme dérivé de `period_start` |
| Valable **même déconnecté** | Le renouvellement est calculé à partir de l'heure écoulée : dès la prochaine requête ou à chaque tour de boucle, il s'applique rétroactivement |
| **Non cumulatif** (remise à 200) | À chaque heure pleine écoulée : `solde = 200` (jamais × N heures) |
| Solde + compte à rebours affichés | Badge en barre supérieure avec `⏳ mm:ss` avant le prochain versement |
| Solde insuffisant ⇒ **blocage + message** | HTTP 402 avec message explicite (coût, solde, délai avant renouvellement) |
| Déduction **côté serveur uniquement** | Aucun montant n'est calculé dans le navigateur pour la validation |
| **Anti-double-déduction / anti-abus** | `SELECT … FOR UPDATE` (verrou de ligne) + `request_id` unique ⇒ une seule déduction par demande, même en cas de requêtes simultanées |
| **Remboursement automatique** si échec | Statut `FAILED` ⇒ `refund_credits()` (idempotent, journalisé) |
| Audit complet | Chaque mouvement écrit dans `credit_ledger` (delta, solde après, acteur, raison) |

**Sécurité complémentaire :** mots de passe PBKDF2-SHA256 (390 000 itérations, jamais en clair), jetons JWT signés + expiration, blocage après 5 échecs de connexion / 15 min, toutes les routes admin vérifiées **en base** (le rôle n'est jamais lu du client), transactions SQL pour soldes exacts, suppression de compte en cascade.

---

## 🛠️ API (aperçu)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | Inscription / connexion |
| POST | `/api/chat` | Message au chat IA |
| POST | `/api/images` · `/api/videos` · `/api/code` | Générations |
| GET | `/api/generations/{id}` | Suivi d'une tâche longue (polling) |
| GET | `/api/gallery` · `/api/conversations` | Galerie / historique |
| GET/PATCH | `/api/me` · `/api/me/credits/history` | Profil, solde, journal de crédits |
| GET | `/api/admin/stats` · `/api/admin/users` · `/api/admin/settings` · `/api/admin/logs` | Administration (ADMIN requis) |
| POST | `/api/admin/users/{id}/credits` · `/api/admin/credits/all` | Opérations de crédits journalisées |
| PUT | `/api/admin/settings` | Coûts, renouvellement, fonctions IA, limites |

Documentation interactive : **http://localhost:8000/docs** (routes publiques).

---

## ☁️ Déploiement sur Render (recommandé, gratuit)

Le fichier **`render.yaml`** à la racine contient toute la configuration : Render le lit
automatiquement et crée **le service web + la base PostgreSQL** en une seule opération.
Vous n'avez rien d'autre à écrire.

### 1. Publier le code sur GitHub

Render récupère le code depuis un dépôt Git. Si `git` n'est pas installé, utilisez
[GitHub Desktop](https://desktop.github.com/) ou installez `git`, puis :

```bash
git init
git add .
git commit -m "KYRO AI"
git remote add origin https://github.com/VOTRE-COMPTES/kyro-ai.git
git push -u origin main
```

> `.env`, `.env.postgres`, `.pg_super_password.txt` et `kyro_local.db` sont ignorés
> (`.gitignore`) : **aucun secret ne part sur GitHub.**

### 2. Créer le service sur Render

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**
2. Connectez votre dépôt GitHub `kyro-ai`
3. Render détecte `render.yaml` → cliquez **Apply**

Render crée alors :
- un service web **`kyro-ai`** (Python, `uvicorn … --port $PORT`)
- une base **`kyro-db`** PostgreSQL liée, dont l'URL est injectée dans `KYRO_DATABASE_URL`

### 3. Créer le compte administrateur

Ajoutez ces variables (**Environment** → **Add Environment Variable**) :

| Variable | Valeur |
|---|---|
| `ADMIN_EMAIL` | `admin@kyro-ai.com` |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | *(mot de passe fort, 8 caractères min.)* |

Au **premier démarrage**, le serveur crée cet admin s'il n'en existe aucun — puis ne
le recrée jamais (non bloquant si les variables sont absentes). Côté serveur uniquement,
jamais par requête HTTP.

### 4. Configurer les fournisseurs IA (optionnel)

**Environment** → **Add Environment Variable** pour chacun :

```
KYRO_CHAT_API_BASE   https://api.openai.com/v1
KYRO_CHAT_API_KEY    sk-...
KYRO_CHAT_MODEL      gpt-4o-mini
KYRO_IMAGE_API_BASE  https://api.openai.com/v1
KYRO_IMAGE_API_KEY   sk-...
KYRO_VIDEO_API_KEY   r8_...
KYRO_VIDEO_MODEL     ...
```

Tant qu'ils sont absents, l'API répond « fournisseur non configuré » (503) **sans débiter**.

### 5. Après le premier déploiement

- **Environment** → remplacez `KYRO_CORS_ORIGINS` = `*` par l'URL exacte du service
  (`https://kyro-ai-xxxx.onrender.com`)
- **Environment** → `KYRO_JWT_SECRET` est déjà généré aléatoirement par Render
- Le domaine (`*.onrender.com`) est déjà en **HTTPS** automatiquement

> ⚠️ **Limites du plan gratuit à connaître :**
> 1. La base PostgreSQL expire **après 90 jours** → upgrader ou exporter avant.
> 2. Le disque est **éphémère** : images/vidéos dans `./media` perdues au
>    redéploiement → plan *Starter* + *persistent disk*, ou stockage externe (S3/R2).
> 3. Après ~15 min d'inactivité le service se met en veille : le 1er chargement est lent.

---

## 🐳 Autres déploiements

### Docker (recommandé pour un VPS)

```bash
cp .env.example .env      # configurer
docker compose up -d --build
docker compose exec web python -m scripts.init_admin
# → http://localhost:8000
```

### Serveur (systemd / VPS)

```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

> ⚠️ Utilisez **1 worker** avec le moteur de tâches intégré, ou passez à Celery/Redis (voir ci-dessous). Placez un **reverse-proxy HTTPS** (Nginx/Caddy) devant l'application et limitez `KYRO_CORS_ORIGINS` à votre domaine en production.

### Passer à l'échelle (multi-instances)

Le moteur de tâches utilise `asyncio` (adapté à une instance unique). Pour plusieurs instances : **Celery + Redis** — le routeur ne fait que créer la tâche et débiter les crédits ; le worker exécuterait `services/ai.py` avec les mêmes règles de remboursement.

---

## ✅ Vérification rapide

1. Inscrivez-vous sur `#/inscription` → **200 crédits** creditedés immédiatement.
2. Envoyez un message au chat → solde passe à **197**, `⏳` décompte dans la barre.
3. Déconnectez-vous ~1 h → reconnectez-vous : le solde est de nouveau à **200** (non cumulatif).
4. Coupez `KYRO_CHAT_API_KEY` → le chat affiche le message « fournisseur non configuré » et **rembourse** les crédits.
5. Connectez-vous avec l'ADMIN → `#/admin` : statistiques, utilisateurs, crédits, paramètres, journaux.
6. Testez le blocage : retirez des crédits à un compte (admin) → la demande est refusée avec un message explicatif.

---

## 📄 Licence

Projet Kyro AI — tous droits réservés.
